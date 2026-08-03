"""PROPRIETARY / POTENTIAL IP — spring-force & load-distribution model.

⚠  This module is the potential-IP core of the force model. The repository is
   PRIVATE, so this file IS committed — but it is deliberately kept ISOLATED and
   FLAGGED so it can be separated out again if the repo is ever made public:
     • the filename ends in `_ip.py` and every public function carries the `_IP`
       suffix — grep markers for "the IP";
     • `calibration.py` imports it behind a try/except (`_HAS_MODEL_IP`), so the
       app still runs with this file removed — its channels simply aren't produced.
   To publish: pull this file out and re-gitignore `*_ip.py`; nothing else changes.

The output channels use `*_Load_*` names (chosen when this was briefly concealed
in a then-public repo); they are the spring-force-derived vertical tire loads.
"""
import numpy as np


def apply_model_IP(df, k_f, k_r, pl_f, pl_r, hta_deg, mr_shock, mr_wheel):
    """Add the load channels to ``df`` in place and return it.

    Public entry point for the load model. Inputs: front/rear spring rate (N/mm),
    front/rear preload (mm), head-tube angle (deg), and the motion-ratio LUT
    (shock-travel, wheel-travel arrays). The front weight-distribution channel is
    produced SEPARATELY by ``front_weight_bias_IP`` — it must run after the
    filtered-pitch twin (``Filt_Pitch_deg``) exists.
    """
    _shaft_spring_force(df, k_f, k_r, pl_f, pl_r)
    _vertical_force_distribution(df, hta_deg, mr_shock, mr_wheel)
    return df


def static_pedal_front_bias_IP(chainstay, front_center):
    """LEVEL-GROUND FRONT weight distribution (%) with the rider's weight applied
    ONLY at the bottom bracket (standing on the pedals) — the θ=0 base constant.

    GOVERNING ASSUMPTION (bike-only static analysis): the free body is the BIKE
    alone, and the only external forces act at three points — the two tire
    contact patches and the bottom bracket. Quasi-static, no rider-CoG height, no
    fore/aft accel, braking, or pedaling torque (all intentionally excluded).
    With a vertical load W at the BB and two vertical contact-patch reactions on
    LEVEL ground, it reduces to a beam moment balance: the front reaction is
    proportional to the load's horizontal distance from the REAR axle
    (= chainstay), so
        front% = 100 · chainstay / (chainstay + front_center)
               = 100 · chainstay / wheelbase.
    (The BB sits closer to the rear axle than the front, so the rear carries the
    larger share.) The bike-PITCH correction is layered on in
    ``front_weight_bias_IP``. Returns NaN if the geometry is unusable.
    """
    try:
        wb = chainstay + front_center
        if wb > 0:
            return 100.0 * chainstay / wb
    except TypeError:
        pass
    return float("nan")


def front_weight_bias_IP(df, chainstay, front_center, bb_height):
    """FRONT weight distribution (%), quasi-static (rider weight only at the BB),
    now corrected for the measured bike PITCH via the FILTERED pitch signal
    (``df['Filt_Pitch_deg']``, nose-up positive). Writes ``Pedal_Only_Ref_Bias_Perc``
    — a time series that reduces to the level-ground constant at zero pitch.

    When the bike pitches by θ, the load point (BB, at height ``bb_height`` above
    the contact line) swings horizontally, transferring weight. The θ-scaling of
    the horizontal wheelbase cancels in the ratio, leaving only the BB-height term:
        front%(θ) = base − (bb_height / wheelbase) · tan(θ) · 100
    where base = ``static_pedal_front_bias_IP`` = 100·chainstay/wheelbase. Nose-up
    (climbing, θ>0) shifts weight rearward; nose-down (descending) forward. Uses
    the filtered pitch so the estimate follows the sustained grade, not bumps.
    NOTE: ``Pitch_deg`` is relative to the record-start pose (no absolute datum),
    so θ here is measured from that reference attitude, not true horizontal.

    Falls back to the constant base if ``bb_height`` or ``Filt_Pitch_deg`` is
    unavailable. Returns ``df``.
    """
    import numpy as np
    base = static_pedal_front_bias_IP(chainstay, front_center)
    if not np.isfinite(base):
        return df
    wb = (chainstay or 0.0) + (front_center or 0.0)
    pitch = df["Filt_Pitch_deg"] if "Filt_Pitch_deg" in df.columns else None
    if (pitch is not None and bb_height is not None
            and np.isfinite(bb_height) and wb > 0):
        df["Pedal_Only_Ref_Bias_Perc"] = (
            base - (bb_height / wb) * np.tan(np.radians(pitch.values)) * 100.0)
    else:
        df["Pedal_Only_Ref_Bias_Perc"] = base
    return df


def _shaft_spring_force(df, k_f, k_r, pl_f, pl_r):
    """Spring-only SHAFT forces (damper deliberately ignored), linear
    ``F = k · (shaft displacement + preload)``. Preload = initial shaft
    compression at 0 % stroke (mm) — a real coil sits compressed even topped out.
    Writes ``Fork_Load_N`` / ``Shock_Load_N`` (each only when its rate is finite
    and its position column exists)."""
    if np.isfinite(k_f) and "Fork_Pos_mm" in df.columns:
        df["Fork_Load_N"] = k_f * (df["Fork_Pos_mm"] + pl_f)
    if np.isfinite(k_r) and "Shock_Pos_mm" in df.columns:
        df["Shock_Load_N"] = k_r * (df["Shock_Pos_mm"] + pl_r)


def _vertical_force_distribution(df, hta_deg, mr_shock, mr_wheel):
    """Vertical (bike-Z) tire load from each shaft force, and the front/rear
    load-distribution bias:

      * front — the fork shaft is inclined at the head angle from horizontal, so
        ``F_vert = F_shaft · sin(HTA)``.
      * rear  — virtual work through the linkage: ``F_wheel = F_shock / MR(x)``,
        where the LOCAL motion ratio ``MR(x) = d(wheel)/d(shock)`` is the gradient
        of the motion-ratio lookup, interpolated at each ``Shock_Pos_mm`` (guarded
        ``MR > 0.1``).
      * bias  — ``Front_Load_Bias_Perc = 100 · Fv / (Fv + Rv)``, NaN when the
        total is < 1 N (unloaded / airborne).

    Writes ``Front_/Rear_Vert_Load_N`` and ``Front_Load_Bias_Perc``."""
    if ("Fork_Load_N" in df.columns
            and hta_deg is not None and np.isfinite(hta_deg)):
        df["Front_Vert_Load_N"] = (
            df["Fork_Load_N"] * np.sin(np.radians(hta_deg)))

    if ("Shock_Load_N" in df.columns
            and mr_shock is not None and mr_wheel is not None
            and len(mr_shock) >= 2):
        _s  = np.asarray(mr_shock, dtype=float)
        _wl = np.asarray(mr_wheel, dtype=float)
        _order = np.argsort(_s)
        _s, _wl = _s[_order], _wl[_order]
        _mr_local = np.gradient(_wl, _s)                      # d(wheel)/d(shock)
        _mr_at = np.interp(df["Shock_Pos_mm"].values, _s, _mr_local)
        with np.errstate(divide="ignore", invalid="ignore"):
            df["Rear_Vert_Load_N"] = (
                df["Shock_Load_N"].values
                / np.where(_mr_at > 0.1, _mr_at, np.nan))

    if ("Front_Vert_Load_N" in df.columns
            and "Rear_Vert_Load_N" in df.columns):
        _fv = df["Front_Vert_Load_N"].values
        _rv = df["Rear_Vert_Load_N"].values
        _tot = _fv + _rv
        with np.errstate(divide="ignore", invalid="ignore"):
            df["Front_Load_Bias_Perc"] = np.where(
                _tot > 1.0, 100.0 * _fv / _tot, np.nan)
