import math
import pygame
import settings


class Enemy:
    def __init__(self, x, y, enemy_type, enemy_assets, speed=settings.DEFAULT_ENEMY_SPEED):
        self.x = x
        self.y = y
        self.enemy_type = enemy_type
        self.speed = speed

        self.frames = enemy_assets[enemy_type]
        self.frame_index = 0
        self.animation_timer = 0
        self.animation_speed = 8
        self.image = self.frames[self.frame_index]
        self.rect = self.image.get_rect(center=(int(self.x), int(self.y)))

        self.facing_left = False
        self.knockback_dx = 0
        self.knockback_dy = 0
        self.knockback_dist_remaining = 0
        self.health = settings.ENEMY_MAX_HEALTH

    def update(self, player):
        if self.knockback_dist_remaining > 0:
            self.apply_knockback()
        else:
            self.move_toward_player(player)

        self.animate()

    def move_toward_player(self, player):
        dx = player.x - self.x
        dy = player.y - self.y
        dist = math.hypot(dx, dy)

        if dist != 0:
            self.x += (dx / dist) * self.speed
            self.y += (dy / dist) * self.speed

        self.facing_left = dx < 0
        self.rect.center = (int(self.x), int(self.y))

    def apply_knockback(self):
        step = min(settings.ENEMY_KNOCKBACK_SPEED, self.knockback_dist_remaining)
        self.knockback_dist_remaining -= step

        self.x += self.knockback_dx * step
        self.y += self.knockback_dy * step
        self.facing_left = self.knockback_dx < 0
        self.rect.center = (int(self.x), int(self.y))

    def animate(self):
        self.animation_timer += 1
        if self.animation_timer >= self.animation_speed:
            self.animation_timer = 0
            self.frame_index = (self.frame_index + 1) % len(self.frames)
            center = self.rect.center
            self.image = self.frames[self.frame_index]
            self.rect = self.image.get_rect()
            self.rect.center = center

    def draw(self, surface):
        image = self.image
        if self.facing_left:
            image = pygame.transform.flip(self.image, True, False)
        surface.blit(image, self.rect)

    def set_knockback(self, px, py, dist):
        dx = self.x - px
        dy = self.y - py
        length = math.sqrt(dx * dx + dy * dy)
        if length != 0:
            self.knockback_dx = dx / length
            self.knockback_dy = dy / length
            self.knockback_dist_remaining = dist

    def take_damage(self, amount):
        self.health -= amount
        return self.health <= 0
