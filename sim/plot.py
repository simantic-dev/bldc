"""Read a `sim --record` directory and the run log: TIM1 pad edges (gpio.jsonl) -> PWM period, dead time and duty per
phase; the scripted host's COMM_GET_VALUES lines -> the firmware's own telemetry. Writes a PNG, prints the numbers."""
import json, re, sys, statistics as st
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

rec, out, log = sys.argv[1], sys.argv[2], sys.argv[3]
PADS = {("gpioPortA", 8): "U", ("gpioPortA", 9): "V", ("gpioPortA", 10): "W", ("gpioPortB", 13): "Un"}
ev = {k: [] for k in PADS.values()}
for l in open(f"{rec}/gpio.jsonl"):
    d = json.loads(l)
    k = PADS.get((d["port"], d["pin"]))
    if k:
        ev[k].append((d["t"], d["level"]))

def cycles(e):
    """(rise time, period, duty) for every complete high pulse."""
    rises = [t for t, v in e if v]
    falls = [t for t, v in e if not v]
    out, j = [], 0
    for r0, r1 in zip(rises, rises[1:]):
        while j < len(falls) and falls[j] < r0:
            j += 1
        if j < len(falls) and falls[j] < r1:
            out.append((r0, r1 - r0, (falls[j] - r0) / (r1 - r0)))
    return out

cy = {p: cycles(ev[p]) for p in "UVW"}
log_t = open(log).read()
cmds = [(float(m[1]), float(m[2])) for m in re.finditer(r"CMD t=([\d.]+) COMM_SET_DUTY ([\d.]+)", log_t)]
vals = [dict(t=float(m[1]), duty=float(m[2]), vin=float(m[3]), fault=int(m[4]))
        for m in re.finditer(r"VESC t=([\d.]+) .*? duty=(-?[\d.]+) vin=([\d.]+) .*?fault=(\d+)", log_t)]
fw = re.search(r"FWV t=([\d.]+) version=(\S+) hw=(\S+)", log_t)
tim1 = re.search(r"TIM1 t=9.50 CR1=(\S+) PSC=(\d+) ARR=(\d+) BDTR=(\S+) .*", log_t)

# command windows: [start, next start); skip 0.3 s after each change for the firmware's duty ramp
win = []
for (t0, d), nxt in zip(cmds, [c[0] for c in cmds[1:]] + [cmds[-1][0] + 1.0]):
    win.append((t0 + 0.3, nxt, d))
first_pwm = min(ev["U"][1][0], ev["U"][2][0])
period = st.median(c[1] for p in "UVW" for c in cy[p][1000:3000])
fallU = [t for t, v in ev["U"] if not v]
riseUn = [t for t, v in ev["Un"] if v]
import bisect
dead = []
for f in fallU[1000:3000]:
    i = bisect.bisect_right(riseUn, f)
    if i < len(riseUn):
        dead.append(riseUn[i] - f)
dead_ns = st.median(dead) * 1e9

def wmean(p, a, b):
    x = [c[2] for c in cy[p] if a <= c[0] < b]
    return 100 * st.mean(x) if x else float("nan")

fig, ax = plt.subplots(4, 1, figsize=(10, 13), constrained_layout=True)
cols = {"U": "#1f77b4", "V": "#d62728", "W": "#2ca02c"}
for p, ls in zip("UVW", ("-", "-", (0, (2, 3)))):
    x = [c for c in cy[p] if c[0] > 6][::40]
    ax[0].plot([c[0] for c in x], [100 * c[2] for c in x], lw=1.2, ls=ls, color=cols[p], label=f"phase {p}")
ax[0].set(ylabel="pad high-time (%)", ylim=(35, 66), xlim=(6, 13), title="VESC 75_300 firmware on a STM32F405 sim: TIM1 pad duty (cmd 5, 10, 20, 0 % at 8-11 s)")
ax[0].legend(loc="upper left", ncol=3, fontsize=8)
z0 = 10.5
for p, c, off, nm in (("U", "#1f77b4", 2.5, "PA8 (TIM1_CH1)"), ("Un", "#9467bd", 0, "PB13 (TIM1_CH1N)")):
    e = [(t, v) for t, v in ev[p] if z0 - 1e-6 <= t <= z0 + 2.2 * period]
    ax[1].step([(t - z0) * 1e6 for t, v in e], [v + off for t, v in e], where="post", color=c, label=nm)
ax[1].set(xlabel="us", yticks=[], title=f"two PWM periods at duty 0.20: period {period*1e6:.2f} us, dead time {dead_ns:.0f} ns (PA8 low to PB13 high)")
ax[1].legend(loc="upper right")
ax[2].plot([v["t"] for v in vals], [v["duty"] * 100 for v in vals], lw=1, color="#ff7f0e", label="duty in COMM_GET_VALUES (%)")
ax[2].step([c[0] for c in cmds] + [13], [100 * c[1] for c in cmds] + [cmds[-1][1] * 100], where="post", color="k", ls="--", label="commanded (%)")
ax[2].set(ylabel="%", title="firmware telemetry (COMM_GET_VALUES every 50 ms)")
ax[2].legend(loc="upper left", fontsize=8)
ax[3].plot([v["t"] for v in vals], [v["vin"] for v in vals], color="#8c564b")
ax[3].set(xlabel="virtual time (s)", ylabel="V", title="vin in telemetry: follows the scripted ADC stimulus (48 V, then 44 V at 9.5 s)")
fig.savefig(out, dpi=110)

print(f"firmware version reply: {fw[2]} hw {fw[3]}" if fw else "no version reply")
print(f"TIM1 registers read back at 9.5 s: CR1={tim1[1]} PSC={tim1[2]} ARR={tim1[3]} BDTR={tim1[4]}" if tim1 else "no TIM1 probe line")
print(f"first PWM edges {first_pwm:.4f} s; period {period*1e6:.2f} us = {1/period/1e3:.2f} kHz; cycles U/V/W {len(cy['U'])}/{len(cy['V'])}/{len(cy['W'])}")
print(f"dead time PA8 fall -> PB13 rise: {dead_ns:.0f} ns")
for a, b, d in win:
    print(f"command {d:.2f}: pad duty U {wmean('U', a, b):.2f} %  V {wmean('V', a, b):.2f} %  W {wmean('W', a, b):.2f} %"
          f"; V-U {wmean('V', a, b) - wmean('U', a, b):.2f} pts (duty x sqrt3/2 = {100 * d * 3 ** .5 / 2:.2f})"
          f"; telemetry duty {st.mean([v['duty'] for v in vals if a <= v['t'] < b]):.3f}")
print(f"telemetry: {len(vals)} COMM_GET_VALUES replies; vin {st.median([v['vin'] for v in vals if v['t']>8 and v['t']<9.4]):.1f} V (stimulus 48.0) then "
      f"{st.median([v['vin'] for v in vals if v['t']>10]):.1f} V (stimulus 44.0); fault codes seen: {sorted({v['fault'] for v in vals})}")
