import numpy as np
p = np.load("data/sequences_v2/preprocessing_parameters.npz")
names = [str(n) for n in p["continuous_feature_names"]]
scale = dict(zip(names, p["continuous_scaler_scale"]))
d = np.load("data/sequences_v2/test.npz")
X, y = d["X"], d["y"]
n = X[y == 0]
cont, miss = n[:, :, :8], n[:, :, 8:]

# 1) identical-consecutive-row runs in normal windows
diff = np.abs(np.diff(cont, axis=1))
same = diff.sum(axis=2) < 1e-6
run = np.zeros(len(n), int); best = np.zeros(len(n), int)
for t in range(same.shape[1]):
    run = np.where(same[:, t], run + 1, 0)
    best = np.maximum(best, run)
print("normal windows with run>=3 identical steps:", round(float((best >= 3).mean()), 3))
print("longest-run quantiles (50/75/90/99):", np.percentile(best, [50, 75, 90, 99]))

# 2) per-step standardized lat/lon movement vs spoof offset
dlat = diff[:, :, 0].ravel(); dlon = diff[:, :, 1].ravel()
dlat = dlat[dlat > 0]; dlon = dlon[dlon > 0]
print("normal per-step |dlat| (std units) median/90/99:", np.percentile(dlat, [50, 90, 99]).round(5))
print("normal per-step |dlon| (std units) median/90/99:", np.percentile(dlon, [50, 90, 99]).round(5))
print("spoof offset lat (std units):", round(0.15 / scale["lat"], 5), " lon:", round(0.20 / scale["lon"], 5))

# 3) missingness in normal windows
print("normal windows with any lat missing:", round(float(miss[:, :, 0].any(axis=1).mean()), 3))
print("normal windows with any velocity missing:", round(float(miss[:, :, 2].any(axis=1).mean()), 3))
