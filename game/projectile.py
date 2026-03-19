import math
import pygame
import settings


class Projectile:
    def __init__(self, x, y, target_x, target_y, damage=None, speed=None, radius=None):
        self.x = x
        self.y = y
        self.damage = damage if damage is not None else settings.PLAYER_RANGED_DAMAGE
        self.speed = speed if speed is not None else settings.PLAYER_RANGED_SPEED
        self.radius = radius if radius is not None else settings.PLAYER_PROJECTILE_RADIUS

        dx = target_x - x
        dy = target_y - y
        length = math.hypot(dx, dy)
        if length == 0:
            self.dir_x = 1.0
            self.dir_y = 0.0
        else:
            self.dir_x = dx / length
            self.dir_y = dy / length

        self.rect = pygame.Rect(0, 0, self.radius * 2, self.radius * 2)
        self.rect.center = (int(self.x), int(self.y))

    def update(self):
        self.x += self.dir_x * self.speed
        self.y += self.dir_y * self.speed
        self.rect.center = (int(self.x), int(self.y))

    def is_offscreen(self):
        margin = self.radius * 2
        return (
            self.x < -margin
            or self.x > settings.WIDTH + margin
            or self.y < -margin
            or self.y > settings.HEIGHT + margin
        )

    def draw(self, surface):
        pygame.draw.circle(surface, (70, 210, 255), self.rect.center, self.radius)
