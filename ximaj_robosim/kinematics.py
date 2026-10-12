"""Kinematik fuer generische 6-Achs-Knickarmroboter (mm / Grad). Eigenentwicklung der Ximaj IT Solutions.

Kette:  Rz(A1) T(a1,0,d1) Ry(90+A2) T(0,0,a2) Ry(A3) T(-a3,0,d4) Rz(A4) Ry(A5) Rz(A6) T(0,0,d6)
Home = (0,-90,90,0,0,0): Oberarm senkrecht, Unterarm waagrecht nach vorn. A5 = 90 -> Werkzeug zeigt nach unten.
Flansch-Z zeigt aus dem Flansch heraus. Pose-Konvention: R = Rz(A) Ry(B) Rx(C).
"""
import math
import numpy as np

D2R = math.pi / 180.0
R2D = 180.0 / math.pi


def rx(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0, 0], [0, c, -s, 0], [0, s, c, 0], [0, 0, 0, 1.0]])


def ry(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s, 0], [0, 1, 0, 0], [-s, 0, c, 0], [0, 0, 0, 1.0]])


def rz(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0, 0], [s, c, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1.0]])


def tr(x, y, z):
    m = np.eye(4)
    m[:3, 3] = (x, y, z)
    return m


def pose_to_mat(x, y, z, a, b, c):
    m = rz(a * D2R) @ ry(b * D2R) @ rx(c * D2R)
    m[:3, 3] = (x, y, z)
    return m


def mat_to_pose(m):
    r = m[:3, :3]
    cb = math.hypot(r[0, 0], r[1, 0])
    if cb > 1e-9:
        a = math.atan2(r[1, 0], r[0, 0])
        b = math.atan2(-r[2, 0], cb)
        c = math.atan2(r[2, 1], r[2, 2])
    else:
        a = 0.0
        b = math.copysign(math.pi / 2, -r[2, 0])
        c = math.atan2(-r[1, 2], r[1, 1]) if r[2, 0] < 0 else -math.atan2(-r[1, 2], r[1, 1])
    return np.array([m[0, 3], m[1, 3], m[2, 3], a * R2D, b * R2D, c * R2D])


def inv(m):
    r = m[:3, :3].T
    o = np.eye(4)
    o[:3, :3] = r
    o[:3, 3] = -r @ m[:3, 3]
    return o


def wrap(a):
    return (a + 180.0) % 360.0 - 180.0


class RobotModel:
    def __init__(self, name, a1, d1, a2, a3, d4, d6, limits, vmax, payload):
        self.name = name
        self.a1, self.d1, self.a2, self.a3, self.d4, self.d6 = a1, d1, a2, a3, d4, d6
        self.limits = np.array(limits, float)
        self.vmax = np.array(vmax, float)
        self.payload = payload
        self.L3 = math.hypot(a3, d4)
        self.phi = math.atan2(-a3, d4)
        self.reach = a2 + self.L3 + d6

    def frames(self, q):
        q = np.asarray(q, float) * D2R
        f0 = np.eye(4)
        f1 = rz(q[0])
        f2 = f1 @ tr(self.a1, 0, self.d1) @ ry(math.pi / 2 + q[1])
        f3 = f2 @ tr(0, 0, self.a2) @ ry(q[2])
        f4 = f3 @ tr(-self.a3, 0, self.d4) @ rz(q[3])
        f5 = f4 @ ry(q[4])
        f6 = f5 @ rz(q[5]) @ tr(0, 0, self.d6)
        return [f0, f1, f2, f3, f4, f5, f6]

    def fk(self, q):
        return self.frames(q)[-1]

    def ik_all(self, T):
        sols = []
        R = T[:3, :3]
        W = T[:3, 3] - self.d6 * R[:, 2]
        base_q1 = math.atan2(W[1], W[0]) if (abs(W[0]) + abs(W[1])) > 1e-9 else 0.0
        for q1 in (base_q1, base_q1 + math.pi):
            r = W[0] * math.cos(q1) + W[1] * math.sin(q1) - self.a1
            z = W[2] - self.d1
            d2 = r * r + z * z
            cb = (d2 - self.a2 ** 2 - self.L3 ** 2) / (2 * self.a2 * self.L3)
            if cb > 1 + 1e-9 or cb < -1 - 1e-9:
                continue
            cb = max(-1.0, min(1.0, cb))
            for sgn in (1, -1):
                beta = sgn * math.acos(cb)
                alpha3 = beta - self.phi
                psi = math.atan2(r, z)
                alpha2 = psi - math.atan2(self.L3 * math.sin(beta), self.a2 + self.L3 * math.cos(beta))
                q2, q3 = alpha2 - math.pi / 2, alpha3
                r03 = rz(q1) @ ry(alpha2 + alpha3)
                r36 = r03[:3, :3].T @ R
                s5 = math.hypot(r36[0, 2], r36[1, 2])
                cands = []
                if s5 > 1e-6:
                    q5 = math.atan2(s5, r36[2, 2])
                    cands.append((math.atan2(r36[1, 2], r36[0, 2]), q5, math.atan2(r36[2, 1], -r36[2, 0])))
                    cands.append((math.atan2(-r36[1, 2], -r36[0, 2]), -q5, math.atan2(-r36[2, 1], r36[2, 0])))
                else:
                    if r36[2, 2] > 0:
                        cands.append((None, 0.0, math.atan2(r36[1, 0], r36[0, 0])))
                    else:
                        cands.append((None, math.pi, math.atan2(r36[1, 0], -r36[0, 0])))
                for q4, q5, q6 in cands:
                    sols.append([q1 * R2D, q2 * R2D, q3 * R2D,
                                 None if q4 is None else q4 * R2D, q5 * R2D, q6 * R2D, r36])
        return sols

    def _fit(self, v, i, ref):
        lo, hi = self.limits[i]
        best = None
        for k in range(-3, 4):
            c = v + 360.0 * k
            if lo - 1e-6 <= c <= hi + 1e-6 and (best is None or abs(c - ref) < abs(best - ref)):
                best = c
        return best

    def status_turn(self, q):
        s = 0
        f = self.frames(q)
        wr = f[4][:3, 3]
        r = wr[0] * math.cos(q[0] * D2R) + wr[1] * math.sin(q[0] * D2R) - self.a1
        if r < 0:
            s |= 1
        if q[2] >= -math.degrees(self.phi):
            s |= 2
        if q[4] < 0:
            s |= 4
        t = 0
        for i in range(6):
            if q[i] < 0:
                t |= 1 << i
        return s, t

    def ik(self, T, q_ref, st=None):
        """Beste Loesung innerhalb der Gelenkgrenzen nahe q_ref; st=(S,T) optional. -> q oder None"""
        q_ref = np.asarray(q_ref, float)
        best, bestc = None, 1e18
        sols = self.ik_all(T)
        # nahe der Handgelenk-Singularitaet: Loesung mit unveraendertem A4 ergaenzen (kein A4/A6-Sprung)
        extra = []
        for s in sols:
            r36 = s[6]
            if math.hypot(r36[0, 2], r36[1, 2]) < 0.08:
                c4 = q_ref[3] * D2R
                Rp = rz(-c4)[:3, :3] @ r36
                if abs(Rp[1, 2]) < 2e-3:
                    extra.append([s[0], s[1], s[2], q_ref[3], math.atan2(Rp[0, 2], Rp[2, 2]) * R2D,
                                  math.atan2(Rp[1, 0], Rp[1, 1]) * R2D, r36])
        for s in sols + extra:
            q = []
            ok = True
            for i in range(6):
                v = s[i] if s[i] is not None else q_ref[i]
                f = self._fit(v, i, q_ref[i])
                if f is None:
                    ok = False
                    break
                q.append(f)
            if not ok:
                continue
            q = np.array(q)
            if s[3] is None:
                q[3] = q_ref[3]
                f6 = self._fit(s[5] - q[3] + 0.0, 5, q_ref[5])
                if f6 is None:
                    continue
                q[5] = f6
            cost = float(np.sum(np.abs(q - q_ref) * np.array([1, 1, 1, .5, .5, .3])))
            if st is not None and self.status_turn(q) != (int(st[0]), int(st[1])):
                cost += 1e4
            if cost < bestc:
                best, bestc = q, cost
        return best

    def in_limits(self, q):
        q = np.asarray(q)
        return bool(np.all(q >= self.limits[:, 0] - 1e-6) and np.all(q <= self.limits[:, 1] + 1e-6))

    def jacobian(self, q, eps=1e-4):
        q = np.asarray(q, float)
        T0 = self.fk(q)
        J = np.zeros((6, 6))
        for i in range(6):
            dq = q.copy()
            dq[i] += eps
            T1 = self.fk(dq)
            J[:3, i] = (T1[:3, 3] - T0[:3, 3]) / (eps * D2R)
            dR = T1[:3, :3] @ T0[:3, :3].T
            J[3:, i] = np.array([dR[2, 1] - dR[1, 2], dR[0, 2] - dR[2, 0], dR[1, 0] - dR[0, 1]]) / 2 / (eps * D2R)
        return J

    def singularity(self, q):
        J = self.jacobian(q)
        J[:3] /= max(self.reach, 1)
        sv = np.linalg.svd(J, compute_uv=False)
        return float(sv[-1] / max(sv[0], 1e-9))


def _lim(a1, a2, a3, a4, a5, a6):
    return [(-a1, a1), a2, a3, (-a4, a4), a5, (-a6, a6)]


# Generische Modelle mit eigenen, gerundeten Phantasie-Massen (keine Herstellerdaten).
MODELS = {
    "XR-5 (0.5 m, 3 kg)": RobotModel("XR-5", 20, 340, 250, 20, 250, 70,
                                       _lim(170, (-170, 50), (-110, 155), 175, (-120, 120), 350),
                                       [250, 250, 250, 340, 340, 530], 3),
    "XR-7 (0.7 m, 4 kg)": RobotModel("XR-7", 22, 360, 350, 28, 340, 75,
                                      _lim(170, (-180, 45), (-120, 156), 180, (-120, 120), 350),
                                      [300, 270, 300, 360, 365, 570], 4),
    "XR-9 (0.9 m, 6 kg)": RobotModel("XR-9", 25, 400, 450, 35, 420, 80,
                                       _lim(170, (-190, 45), (-120, 156), 185, (-120, 120), 350),
                                       [360, 300, 360, 380, 390, 610], 6),
    "XR-11 (1.1 m, 10 kg)": RobotModel("XR-11", 25, 400, 550, 35, 510, 80,
                                         _lim(170, (-190, 45), (-120, 156), 185, (-120, 120), 350),
                                         [300, 225, 225, 380, 310, 490], 10),
    "XR-15 (1.5 m, 12 kg)": RobotModel("XR-15", 120, 480, 650, 100, 650, 120,
                                        _lim(180, (-150, 10), (-120, 155), 340, (-125, 125), 350),
                                        [200, 190, 200, 300, 300, 500], 12),
    "XR-20 (2.0 m, 16 kg)": RobotModel("XR-20", 160, 520, 780, 150, 860, 150,
                                         _lim(185, (-140, -5), (-120, 155), 350, (-125, 125), 350),
                                         [156, 156, 156, 340, 360, 660], 16),
    "XR-27 (2.7 m, 200 kg)": RobotModel("XR-27", 350, 750, 1250, 55, 1400, 250,
                                          _lim(185, (-140, -5), (-120, 155), 350, (-125, 125), 350),
                                          [136, 113, 120, 280, 285, 400], 200),
    "XR-30 (3.0 m, 300 kg)": RobotModel("XR-30", 400, 800, 1350, 60, 1500, 250,
                                         _lim(185, (-140, -5), (-120, 155), 350, (-125, 125), 350),
                                         [100, 90, 100, 190, 190, 250], 300),
    "XR-40 (3.2 m, 500 kg)": RobotModel("XR-40", 450, 900, 1450, 60, 1600, 280,
                                         _lim(185, (-130, -5), (-110, 150), 350, (-120, 120), 350),
                                         [80, 70, 80, 150, 150, 200], 500),
}
HOME = np.array([0, -90, 90, 0, 0, 0], float)

# Herstellervorlagen und eigene Roboter (robot_library) ergaenzen; Fehler dort duerfen den Start nicht verhindern
try:
    import robot_library as _rl
    _rl.register(MODELS, RobotModel)
except Exception as _e:              # pragma: no cover
    print("Roboterbibliothek nicht geladen:", _e)
