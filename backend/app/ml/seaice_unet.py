"""
Multi-horizon U-Net sea-ice forecaster (§7.3).

Architecture:
  Input:  [T_in * C_dyn + S_static + 2, H, W]
    - T_in  = 7 history days
    - C_dyn = concentration (1 channel here; add wind/temp as extra channels)
    - S_static = 1 (land mask)
    - 2 extra = sin(doy), cos(doy) broadcast to H×W
  Output: [L, H, W] residual to add to persistence; clamped to [0,1] after add.

Training discipline (§7.4):
  - Fixed seeds, deterministic flags where feasible.
  - Loss: masked Huber on the concentration prediction, per-cell weights
    upweighting the marginal ice zone (0.15–0.50) and ice-edge band.
  - Early stopping on validation skill vs persistence in the MIZT at median lead.
  - If model does not beat persistence on validation, record the negative result.

DATA GUARD:
  The class itself imposes no data guard.  The guard is in scripts/train_sea_ice.py.

NOTE: This module does NOT require PyTorch at import time — the class is only
      instantiated by the training script, which installs PyTorch explicitly.
      Serving uses the serialised artifact loaded by registry.py.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

T_IN   = 7
C_DYN  = 1    # concentration only (expand when forcing channels added)
S_STAT = 1    # land mask
N_IN   = T_IN * C_DYN + S_STAT + 2   # = 10
MAX_LEAD = 7
MIZT_LO, MIZT_HI = 0.15, 0.50        # marginal ice zone thresholds


@dataclass
class UNetConfig:
    n_in:          int   = N_IN
    max_lead:      int   = MAX_LEAD
    base_channels: int   = 32          # first encoder stage; doubles each stage
    n_stages:      int   = 4
    dropout:       float = 0.1         # bottleneck dropout
    weight_decay:  float = 1e-4
    lr:            float = 3e-4
    max_epochs:    int   = 100
    patience:      int   = 10          # early stopping on val skill
    batch_size:    int   = 8
    patch_size:    int   = 64          # spatial patch for training
    seed:          int   = 0
    mizt_weight:   float = 3.0         # loss weight for MIZT cells
    edge_weight:   float = 2.0         # loss weight for ice-edge cells


def _build_unet(cfg: UNetConfig):
    """Build the U-Net with PyTorch. Called only when torch is available."""
    import torch
    import torch.nn as nn

    class ConvBlock(nn.Module):
        def __init__(self, c_in, c_out):
            super().__init__()
            self.seq = nn.Sequential(
                nn.Conv2d(c_in, c_out, 3, padding=1, bias=False),
                nn.BatchNorm2d(c_out),
                nn.ReLU(inplace=True),
                nn.Conv2d(c_out, c_out, 3, padding=1, bias=False),
                nn.BatchNorm2d(c_out),
                nn.ReLU(inplace=True),
            )
        def forward(self, x): return self.seq(x)

    class UNetModel(nn.Module):
        def __init__(self, cfg: UNetConfig):
            super().__init__()
            self.cfg = cfg
            C = cfg.base_channels
            L = cfg.max_lead

            # Encoder
            self.enc = nn.ModuleList()
            self.pool = nn.ModuleList()
            ch = cfg.n_in
            ch_list = [ch]
            for s in range(cfg.n_stages):
                out_ch = C * (2 ** s)
                self.enc.append(ConvBlock(ch, out_ch))
                self.pool.append(nn.MaxPool2d(2))
                ch = out_ch
                ch_list.append(ch)

            # Bottleneck with dropout
            bn_ch = C * (2 ** cfg.n_stages)
            self.bottleneck = nn.Sequential(
                ConvBlock(ch, bn_ch),
                nn.Dropout2d(p=cfg.dropout),
            )
            ch = bn_ch

            # Decoder
            self.up = nn.ModuleList()
            self.dec = nn.ModuleList()
            for s in reversed(range(cfg.n_stages)):
                skip_ch = ch_list[s + 1]
                up_ch = C * (2 ** s)
                self.up.append(nn.ConvTranspose2d(ch, up_ch, 2, stride=2))
                self.dec.append(ConvBlock(up_ch + skip_ch, up_ch))
                ch = up_ch

            # Head: output L lead maps
            self.head = nn.Conv2d(ch, L, 1)

        def forward(self, x):
            skips = []
            for enc, pool in zip(self.enc, self.pool):
                x = enc(x)
                skips.append(x)
                x = pool(x)
            x = self.bottleneck(x)
            for up, dec, skip in zip(self.up, self.dec, reversed(skips)):
                x = up(x)
                # Handle odd spatial sizes
                if x.shape != skip.shape:
                    import torch.nn.functional as F
                    x = F.interpolate(x, size=skip.shape[2:])
                x = torch.cat([x, skip], dim=1)
                x = dec(x)
            return self.head(x)   # (B, L, H, W) — residuals

    return UNetModel(cfg)


class SeaIceUNet:
    """
    Multi-horizon U-Net sea-ice forecaster (§7.3).

    Attributes:
        max_lead   (int)  — read by the serving stack.
        model_id   (str)  — filled after training.
        model_hash (str)  — SHA-256 of the serialised artifact.
    """

    max_lead = MAX_LEAD

    def __init__(self, cfg: Optional[UNetConfig] = None):
        self.cfg = cfg or UNetConfig()
        self._net = None     # lazy, only built when torch available
        self.model_id:   str = ""
        self.model_hash: str = ""
        self.provenance: dict = {}
        self._val_skill_history: List[float] = []

    # ── Training ──────────────────────────────────────────────────────────────

    def fit(
        self,
        conc: np.ndarray,        # (T, H, W)
        dates,
        train_idx: List[int],
        land_mask: Optional[np.ndarray] = None,
        wind_u: Optional[np.ndarray] = None,
        wind_v: Optional[np.ndarray] = None,
        temp2m: Optional[np.ndarray] = None,
        val_idx: Optional[List[int]] = None,
    ) -> dict:
        """
        Train the U-Net per §7.4.  Returns training metadata.
        Requires PyTorch; raises ImportError if absent.
        """
        try:
            import torch
            import torch.nn as nn
            import torch.optim as optim
        except ImportError as exc:
            raise ImportError(
                "PyTorch required to train SeaIceUNet.  "
                "Install torch before running scripts/train_sea_ice.py."
            ) from exc

        cfg = self.cfg
        torch.manual_seed(cfg.seed)
        np.random.seed(cfg.seed)

        net = _build_unet(cfg)
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        net = net.to(device)

        optimizer = optim.AdamW(
            net.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay
        )

        T, H, W = conc.shape
        best_val_skill = float("-inf")
        best_state = None
        no_improve = 0

        SENTINEL = -2.0    # land fill value

        def _make_input(idx: int) -> np.ndarray:
            """Build (N_IN, H, W) input tensor for issue time idx."""
            frames = []
            for lag in range(T_IN - 1, -1, -1):
                src_i = max(0, idx - lag)
                f = conc[src_i].copy()
                if land_mask is not None:
                    f[land_mask] = SENTINEL
                frames.append(f)
            static = (~land_mask).astype(np.float32) if land_mask is not None \
                      else np.ones((H, W), np.float32)
            doy = dates[idx].timetuple().tm_yday
            sin_d = np.full((H, W), np.sin(2 * np.pi * doy / 365.25))
            cos_d = np.full((H, W), np.cos(2 * np.pi * doy / 365.25))
            return np.stack(frames + [static, sin_d, cos_d], axis=0).astype(np.float32)

        def _weight_mask(issue_field: np.ndarray) -> np.ndarray:
            """Per-cell loss weight based on regime at issue time."""
            w = np.ones((H, W), np.float32)
            mizt = (issue_field >= MIZT_LO) & (issue_field < MIZT_HI)
            edge = (issue_field >= MIZT_LO - 0.05) & (issue_field < MIZT_LO + 0.05)
            w[mizt] = cfg.mizt_weight
            w[edge] = cfg.edge_weight
            if land_mask is not None:
                w[land_mask] = 0.0
            return w

        logger.info("Training U-Net on %d steps, device=%s", len(train_idx), device)
        for epoch in range(cfg.max_epochs):
            net.train()
            epoch_loss = 0.0
            rng = np.random.default_rng(cfg.seed + epoch)
            shuffled = rng.permutation(train_idx).tolist()
            batch_losses = []

            for b_start in range(0, len(shuffled), cfg.batch_size):
                batch_idx = shuffled[b_start: b_start + cfg.batch_size]
                Xs, Ys, Ws = [], [], []
                for i in batch_idx:
                    max_target = i + cfg.max_lead
                    if max_target >= T:
                        continue
                    # Random spatial crop for memory
                    if H > cfg.patch_size:
                        r0 = rng.integers(0, H - cfg.patch_size)
                        c0 = rng.integers(0, W - cfg.patch_size)
                        ps = cfg.patch_size
                    else:
                        r0, c0, ps = 0, 0, H

                    x_np = _make_input(i)[:, r0:r0+ps, c0:c0+ps]
                    y_np = np.stack([
                        conc[i + l][r0:r0+ps, c0:c0+ps] - conc[i][r0:r0+ps, c0:c0+ps]
                        for l in range(1, cfg.max_lead + 1)
                    ], axis=0).astype(np.float32)
                    issue_crop = conc[i][r0:r0+ps, c0:c0+ps]
                    lm_crop = land_mask[r0:r0+ps, c0:c0+ps] if land_mask is not None \
                              else np.zeros((ps, ps), bool)
                    w_np = np.stack([
                        _weight_mask(issue_crop)[r0:r0+ps, c0:c0+ps]
                        if lm_crop.shape == (ps, ps) else _weight_mask(issue_crop)
                        for _ in range(cfg.max_lead)
                    ], axis=0)
                    Xs.append(x_np); Ys.append(y_np); Ws.append(w_np)

                if not Xs:
                    continue

                X_t = torch.tensor(np.stack(Xs), device=device)
                Y_t = torch.tensor(np.stack(Ys), device=device)
                W_t = torch.tensor(np.stack(Ws), device=device)

                optimizer.zero_grad()
                residuals = net(X_t)
                valid = W_t > 0
                loss = nn.functional.huber_loss(
                    residuals[valid], Y_t[valid], reduction="none"
                )
                loss = (loss * W_t[valid]).mean()
                if not torch.isfinite(loss):
                    logger.error("Non-finite loss at epoch %d — halting", epoch)
                    break
                loss.backward()
                optimizer.step()
                batch_losses.append(loss.item())

            if batch_losses:
                epoch_loss = float(np.mean(batch_losses))

            # Validation skill vs persistence (MIZT, median lead)
            if val_idx and epoch % 5 == 0:
                net.eval()
                pers_errs, model_errs = [], []
                median_lead = cfg.max_lead // 2
                with torch.no_grad():
                    for i in val_idx:
                        t_idx = i + median_lead
                        if t_idx >= T:
                            continue
                        x_np = _make_input(i)
                        X_t = torch.tensor(x_np[None], device=device)
                        res = net(X_t).cpu().numpy()[0]  # (L, H, W)
                        pred = np.clip(
                            conc[i] + res[median_lead - 1], 0.0, 1.0
                        )
                        true = conc[t_idx]
                        issue = conc[i]
                        mizt_mask = (
                            (issue >= MIZT_LO) & (issue < MIZT_HI)
                            & (land_mask == False if land_mask is not None
                               else np.ones((H, W), bool))
                        )
                        if mizt_mask.sum() == 0:
                            continue
                        pers_errs.append(np.mean(np.abs(true[mizt_mask] - conc[i][mizt_mask])))
                        model_errs.append(np.mean(np.abs(true[mizt_mask] - pred[mizt_mask])))

                if pers_errs:
                    mean_pers = float(np.mean(pers_errs))
                    mean_model = float(np.mean(model_errs))
                    val_skill = 1 - mean_model / mean_pers if mean_pers > 0 else float("nan")
                    self._val_skill_history.append(val_skill)
                    logger.info(
                        "Epoch %d: loss=%.5f  val_skill_mizt(lead%d)=%.4f",
                        epoch, epoch_loss, median_lead, val_skill,
                    )
                    if val_skill > best_val_skill:
                        best_val_skill = val_skill
                        import copy
                        best_state = copy.deepcopy(net.state_dict())
                        no_improve = 0
                    else:
                        no_improve += 1
                    if no_improve >= cfg.patience:
                        logger.info("Early stopping at epoch %d", epoch)
                        break

        # Restore best checkpoint
        if best_state is not None:
            net.load_state_dict(best_state)
        self._net = net.cpu()

        return {
            "best_val_skill_mizt": best_val_skill,
            "epochs_trained": epoch,
            "n_train": len(train_idx),
            "n_val": len(val_idx) if val_idx else 0,
        }

    # ── Inference ─────────────────────────────────────────────────────────────

    def predict_field(
        self,
        conc: np.ndarray,
        issue_idx: int,
        dates,
        land_mask: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """Return (L, H, W) concentration field, land=NaN, clamped to [0,1]."""
        if self._net is None:
            raise RuntimeError("Model not trained or loaded.")
        import torch
        T_val, H, W = conc.shape
        SENTINEL = -2.0

        frames = []
        for lag in range(T_IN - 1, -1, -1):
            src_i = max(0, issue_idx - lag)
            f = conc[src_i].copy()
            if land_mask is not None:
                f[land_mask] = SENTINEL
            frames.append(f)
        static = (~land_mask).astype(np.float32) if land_mask is not None \
                  else np.ones((H, W), np.float32)
        doy = dates[issue_idx].timetuple().tm_yday
        sin_d = np.full((H, W), np.sin(2 * np.pi * doy / 365.25))
        cos_d = np.full((H, W), np.cos(2 * np.pi * doy / 365.25))
        x_np = np.stack(frames + [static, sin_d, cos_d], axis=0).astype(np.float32)

        self._net.eval()
        with torch.no_grad():
            X_t = torch.tensor(x_np[None])
            res = self._net(X_t).numpy()[0]   # (L, H, W)

        out = np.clip(conc[issue_idx] + res, 0.0, 1.0)   # (L, H, W)
        if land_mask is not None:
            out[:, land_mask] = np.nan
        return out

    # ── Serialisation ─────────────────────────────────────────────────────────

    def save(self, path: Path) -> str:
        import torch
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save({
            "cfg": self.cfg,
            "state_dict": self._net.state_dict() if self._net else None,
            "model_id": self.model_id,
            "provenance": self.provenance,
        }, path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.model_hash = digest
        return digest

    @classmethod
    def load(cls, path: Path) -> "SeaIceUNet":
        import torch
        ckpt = torch.load(path, map_location="cpu")
        obj = cls(cfg=ckpt["cfg"])
        if ckpt["state_dict"] is not None:
            obj._net = _build_unet(ckpt["cfg"])
            obj._net.load_state_dict(ckpt["state_dict"])
        obj.model_id   = ckpt.get("model_id", "")
        obj.provenance = ckpt.get("provenance", {})
        return obj
