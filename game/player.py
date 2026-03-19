import math
import pygame
import settings
from game.projectile import Projectile


class Player:
    def __init__(self, x, y, assets):
        self.x = x
        self.y = y
        self.speed = settings.PLAYER_SPEED
        self.animations = assets["player"]
        self.move_state = "idle"
        self.state = "idle"
        self.frame_index = 0
        self.animation_timer = 0
        self.animation_speed = 8
        self.attack_anim_timer = 0
        self.attack_anim_duration = 8
        self.facing_left = False
        self.max_health = settings.PLAYER_MAX_HEALTH
        self.health = self.max_health
        self.max_mana = settings.PLAYER_MAX_MANA
        self.mana = float(self.max_mana)
        self.mana_regen = settings.PLAYER_MANA_REGEN
        self.pickup_range = settings.PLAYER_PICKUP_RANGE
        self.melee_range = settings.PLAYER_MELEE_RANGE
        self.melee_damage = settings.PLAYER_MELEE_DAMAGE
        self.melee_cooldown = settings.PLAYER_MELEE_COOLDOWN
        self.melee_cooldown_timer = 0
        self.ranged_damage = settings.PLAYER_RANGED_DAMAGE
        self.ranged_cost = settings.PLAYER_RANGED_COST
        self.ranged_cooldown = settings.PLAYER_RANGED_COOLDOWN
        self.ranged_cooldown_timer = 0
        self.projectile_radius = settings.PLAYER_PROJECTILE_RADIUS
        self.projectile_count = settings.PLAYER_PROJECTILE_COUNT

        idle_frames = self.animations.get("idle", [])
        if idle_frames:
            self.image = idle_frames[0]
        else:
            self.image = pygame.Surface((24, 24), pygame.SRCALPHA)
            pygame.draw.rect(self.image, (250, 220, 90), (0, 0, 24, 24))

        self.rect = self.image.get_rect(center=(int(self.x), int(self.y)))

    def set_position(self, x, y):
        self.x = x
        self.y = y
        self.rect.center = (int(self.x), int(self.y))

    def handle_input(self):
        keys = pygame.key.get_pressed()

        vel_x, vel_y = 0, 0
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            vel_x -= self.speed
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            vel_x += self.speed
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            vel_y -= self.speed
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            vel_y += self.speed

        self.move_state = "run" if vel_x or vel_y else "idle"
        if vel_x < 0:
            self.facing_left = True
        elif vel_x > 0:
            self.facing_left = False

        return vel_x, vel_y

    def start_attack_animation(self):
        attack_frames = self.animations.get("attack", [])
        if attack_frames:
            self.attack_anim_duration = max(6, len(attack_frames) * 3)
        else:
            self.attack_anim_duration = 8
        self.attack_anim_timer = self.attack_anim_duration
        self.state = "attack"
        self.frame_index = 0
        self.animation_timer = 0

    def update(self):
        if self.melee_cooldown_timer > 0:
            self.melee_cooldown_timer -= 1
        if self.ranged_cooldown_timer > 0:
            self.ranged_cooldown_timer -= 1
        if self.mana < self.max_mana:
            self.mana = min(self.max_mana, self.mana + self.mana_regen)

        attack_frames = self.animations.get("attack", [])
        is_attacking = self.attack_anim_timer > 0
        if is_attacking:
            self.attack_anim_timer -= 1
            if attack_frames:
                self.state = "attack"
            else:
                self.state = self.move_state
        else:
            self.state = self.move_state

        if self.state == "attack" and attack_frames:
            elapsed = self.attack_anim_duration - self.attack_anim_timer
            frame_count = len(attack_frames)
            frame_index = min(
                frame_count - 1,
                (elapsed * frame_count) // max(1, self.attack_anim_duration),
            )
            self.image = attack_frames[frame_index]
            center = self.rect.center
            self.rect = self.image.get_rect(center=center)
            return

        self.animation_timer += 1
        if self.animation_timer >= self.animation_speed:
            self.animation_timer = 0
            frames = self.animations.get(self.state) or self.animations.get("idle", [])
            if not frames:
                return
            self.frame_index = (self.frame_index + 1) % len(frames)
            self.image = frames[self.frame_index]
            center = self.rect.center
            self.rect = self.image.get_rect(center=center)

    def draw(self, surface):
        image = self.image
        if self.facing_left:
            image = pygame.transform.flip(self.image, True, False)
        surface.blit(image, self.rect)

        if self.attack_anim_timer > 0 and not self.animations.get("attack"):
            progress = self.attack_anim_timer / max(1, self.attack_anim_duration)
            effect_size = max(self.rect.width, self.rect.height) + 24
            effect = pygame.Surface((effect_size, effect_size), pygame.SRCALPHA)
            effect_rect = effect.get_rect(center=self.rect.center)
            arc_rect = pygame.Rect(6, 6, effect_size - 12, effect_size - 12)
            alpha = max(0, min(255, int(160 * progress)))
            slash_color = (255, 235, 150, alpha)
            if self.facing_left:
                start_angle = math.pi - 0.8
                end_angle = math.pi + 0.8
            else:
                start_angle = -0.8
                end_angle = 0.8
            pygame.draw.arc(effect, slash_color, arc_rect, start_angle, end_angle, 4)
            surface.blit(effect, effect_rect)

    def take_damage(self, amount):
        self.health = max(0, self.health - amount)

    def attack_melee(self):
        if self.melee_cooldown_timer > 0:
            return False
        self.melee_cooldown_timer = self.melee_cooldown
        self.start_attack_animation()
        return True

    def cast_spell(self, target_x, target_y):
        if self.ranged_cooldown_timer > 0:
            return []
        if self.mana < self.ranged_cost:
            return []

        self.mana -= self.ranged_cost
        self.ranged_cooldown_timer = self.ranged_cooldown

        base_angle = math.atan2(target_y - self.y, target_x - self.x)
        count = max(1, int(self.projectile_count))
        spread_rad = math.radians(10)
        mid = (count - 1) / 2

        projectiles = []
        for i in range(count):
            angle = base_angle + ((i - mid) * spread_rad)
            target_dx = math.cos(angle) * 100
            target_dy = math.sin(angle) * 100
            projectiles.append(
                Projectile(
                    self.x,
                    self.y,
                    self.x + target_dx,
                    self.y + target_dy,
                    damage=self.ranged_damage,
                    radius=self.projectile_radius,
                )
            )
        return projectiles
