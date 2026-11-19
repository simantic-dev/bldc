"""Read-only probe: logs the TIM1 setup the firmware programmed (RM0090 TIM1: CR1.CMS, PSC, ARR, BDTR.DTG/MOE) at fixed
times, so plot.py can compare it with the pad edges. Writes nothing."""
TIM1 = 0x40010000
AT = (2.0, 9.5)   # seconds


class Peripheral:
    def __init__(self, ctx):
        self.ctx, self.n = ctx, 0
        ctx.schedule_periodic(10_000)

    def on_access(self, req):
        if req.is_init:
            self.ctx.schedule_periodic(10_000)
        req.value = 0

    def on_timer(self):
        self.n += 1
        if round(self.n * 0.01, 2) in AT:
            rd = lambda o: self.ctx.bus_read(TIM1 + o, 4)
            self.ctx.info(f"TIM1 t={self.n * 0.01:.2f} CR1={rd(0):#x} PSC={rd(0x28)} ARR={rd(0x2C)} BDTR={rd(0x44):#x} "
                          f"CCER={rd(0x20):#x} CCR1={rd(0x34)} CCR2={rd(0x38)} CCR3={rd(0x3C)}")
