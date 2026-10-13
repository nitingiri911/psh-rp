PROBE_INTERVAL = 1.0
PROBES = 5
PROBE_GAP = 0.2
WINDOW = 30
HIST = 30
WARMUP = 30
MIN_HIST = 10
N_CONSEC = 3
CLEAR_M = 5
SIGMA_K = 2.0
MIN_STD = 1.5
FIXED_THRESHOLD = 85.0
HARD_CUTOFF = 40.0
ALPHA = 2.0
WEIGHTS = (0.3, 0.2, 0.5)
LAT_MAX = 200.0
JIT_MAX = 50.0
LOSS_MAX = 100.0
FREEZE_MODE = "alert"
PRIMARY = "psh"
VARIANTS = {
    "psh": {"alpha": ALPHA, "adaptive": True, "hard": True},
    "fixed": {"alpha": ALPHA, "adaptive": False, "hard": False},
    "no_trend": {"alpha": 0.0, "adaptive": True, "hard": True},
    "no_hard": {"alpha": ALPHA, "adaptive": True, "hard": False},
}
