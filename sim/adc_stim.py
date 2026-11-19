"""Scripted ADC stimulus for the VESC 75_300 analog front end (hwconf/trampa/75_300/hw_75_300_core.c, hw_75_300_core.h).
NOT a motor or battery model: every value is a constant (or a time table) chosen by this file. Channels, as in the
firmware's hw_setup_adc_channels: CURR1-3 on IN10/IN11/IN12, SENS1-3 on IN0/IN1/IN2, pack voltage IN13 (56k/2.2k
divider), MOSFET NTCs IN3/IN8/IN9, motor NTC IN14. The firmware scales by V_REG 3.44 V; the model ADC is 3.3 V, so
codes are written as volts on 3.3 V and come out exact."""
VBUS = [(0, 48.0), (9.5, 44.0)]                 # volts on the pack, (from seconds, value) table
VDIV = 2200.0 / (56000.0 + 2200.0)
ADC_OF = {10: "adc1", 11: "adc2", 12: "adc3", 0: "adc1", 1: "adc2", 2: "adc3", 13: "adc3",
          3: "adc3", 8: "adc1", 9: "adc2", 14: "adc1"}


class Peripheral:
    def __init__(self, ctx):
        self.ctx = ctx
        self.v, self.n = None, 0
        ctx.schedule_periodic(10_000)

    def on_access(self, req):
        if req.is_init:
            self.ctx.schedule_periodic(10_000)
        req.value = 0

    def adc(self, ch, digits):
        self.ctx.set_property(ADC_OF[ch], f"ch{ch}", max(0.0, min(4095.0, digits)) / 4096 * 3.3)

    def on_timer(self):
        self.n += 1
        t = self.n * 0.01
        v = [x for at, x in VBUS if t >= at][-1]
        if v != self.v:
            self.v = v
            self.ctx.info(f"STIM pack voltage {v:.1f} V")
        for ch in (3, 8, 9, 14):
            self.adc(ch, 2048)                      # 10k NTCs at 25 C
        for ch in (10, 11, 12):
            self.adc(ch, 2048)                      # zero phase current: shunt amplifier mid-scale
        for ch in (0, 1, 2):
            self.adc(ch, 0)                         # phase sense: 0 V (floating, no motor)
        self.adc(13, v * VDIV / 3.44 * 4095)
