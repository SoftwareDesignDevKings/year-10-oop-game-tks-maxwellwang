import pygame
import settings


class Pickup:
    _coin_surface = None
    _xp_surface = None

    def __init__(self, x, y, kind):
        self.kind = kind
        if kind == "gold":
            self.value = settings.GOLD_PER_PICKUP
            self.image = self.get_coin_surface()
        else:
            self.value = settings.XP_PER_PICKUP
            self.image = self.get_xp_surface()

        self.rect = self.image.get_rect(center=(int(x), int(y)))

    @classmethod
    def get_coin_surface(cls):
        if cls._coin_surface is None:
            size = max(settings.PICKUP_SIZE * 2, 24)
            surface = pygame.Surface((size, size), pygame.SRCALPHA)
            center = size // 2
            radius = (size // 2) - 2

            outline = (114, 39, 0)
            rim = (194, 112, 16)
            base = (255, 195, 34)
            inner = (248, 171, 32)
            bright = (255, 235, 117)
            shine = (255, 248, 230)
            soft_shine = (255, 236, 196)

            pygame.draw.circle(surface, outline, (center, center), radius)
            pygame.draw.circle(surface, rim, (center, center), radius - 1)
            pygame.draw.circle(surface, base, (center, center), radius - 3)
            pygame.draw.circle(surface, inner, (center - 1, center + 1), radius - 7, 2)
            pygame.draw.arc(
                surface,
                bright,
                (center - radius + 5, center - radius + 4, (radius - 2) * 2, (radius - 1) * 2),
                0.1,
                2.6,
                3,
            )
            pygame.draw.line(
                surface,
                shine,
                (center - 6, center + 6),
                (center + 5, center - 5),
                4,
            )
            pygame.draw.line(
                surface,
                soft_shine,
                (center - 7, center + 8),
                (center + 4, center - 3),
                2,
            )
            pygame.draw.line(
                surface,
                soft_shine,
                (center + 1, center + 8),
                (center + 8, center + 1),
                3,
            )
            cls._coin_surface = surface
        return cls._coin_surface

    @classmethod
    def get_xp_surface(cls):
        if cls._xp_surface is None:
            size = max(settings.PICKUP_SIZE + 6, 18)
            surface = pygame.Surface((size, size), pygame.SRCALPHA)
            mid = size // 2
            outline = (18, 76, 39)
            fill = (61, 214, 105)
            glow = (178, 255, 192)

            points = [
                (mid, 1),
                (size - 2, mid),
                (mid, size - 2),
                (1, mid),
            ]
            pygame.draw.polygon(surface, outline, points)
            pygame.draw.polygon(
                surface,
                fill,
                [(mid, 3), (size - 4, mid), (mid, size - 4), (3, mid)],
            )
            pygame.draw.line(surface, glow, (mid - 1, 5), (mid + 4, mid), 2)
            pygame.draw.line(surface, glow, (mid - 4, mid), (mid + 1, size - 5), 2)
            cls._xp_surface = surface
        return cls._xp_surface

    def draw(self, surface):
        surface.blit(self.image, self.rect)
