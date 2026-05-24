class Pixer:
    def __init__(self, r: float = 0.0, g: float = 0.0, b: float = 0.0, a: float = 0.0):
        self.r = r
        self.g = g
        self.b = b
        self.a = a

    def preblend(self):
        self.r *= self.a
        self.g *= self.a
        self.b *= self.a

    def postblend(self, sc: float):
        if sc != 0.0:
            self.r /= sc
            self.g /= sc
            self.b /= sc

    def __add__(self, other: "Pixer"):
        return Pixer(
            self.r + other.r, self.g + other.g, self.b + other.b, self.a + other.a
        )

    def __mul__(self, v: float):
        return Pixer(self.r * v, self.g * v, self.b * v, self.a * v)

    def __truediv__(self, v: float):
        return Pixer(self.r / v, self.g / v, self.b / v, self.a / v)
