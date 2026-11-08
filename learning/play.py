#!/usr/bin/env python3
"""Play Dodge yourself on the dodge_rl engine.

    python play.py                     # normal difficulty, patterns and powerups
    python play.py --difficulty hard   # the setting training uses
    python play.py --scale 4           # smaller window
    python play.py --seed 3            # fixed game seed

Controls: arrows or WASD to move, X/V or Z/C to start the next game after a
death, Escape to quit.
"""

import argparse
import secrets
import sys

import pygame

from dodge.actions import ACTION_MASKS, DOWN, LEFT, RIGHT, UP
from dodge.display import GameWindow
from dodge.engine import DIFFICULTIES, Engine


# PICO-8 button index -> keys that press it
KEYMAP = {
    0: (pygame.K_LEFT, pygame.K_a),
    1: (pygame.K_RIGHT, pygame.K_d),
    2: (pygame.K_UP, pygame.K_w),
    3: (pygame.K_DOWN, pygame.K_s),
    4: (pygame.K_z, pygame.K_c),
    5: (pygame.K_x, pygame.K_v),
}

RESTART = (1 << 4) | (1 << 5)


def button_mask(pressed):
    mask = 0
    for index, keys in KEYMAP.items():
        if any(pressed[k] for k in keys):
            mask |= 1 << index
    return mask


def action_for(mask):
    """The movement action for a button mask; opposite directions cancel."""
    move = mask & (LEFT | RIGHT | UP | DOWN)
    if move & LEFT and move & RIGHT:
        move &= ~(LEFT | RIGHT)
    if move & UP and move & DOWN:
        move &= ~(UP | DOWN)
    return ACTION_MASKS.index(move)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scale", type=int, default=5, help="window scale (default 5)")
    parser.add_argument("--seed", type=int, default=None,
                        help="seed of the first game (default: random)")
    parser.add_argument("--difficulty", choices=("easy", "normal", "hard"), default="normal")
    parser.add_argument("--patterns", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--powerups", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--frames", type=int, default=None,
                        help="run this many frames then exit "
                             "(default: unlimited, i.e. run until closed)")
    args = parser.parse_args()

    window = GameWindow(scale=args.scale)
    seed = args.seed if args.seed is not None else secrets.randbelow(2**31 - 1)
    engine = Engine(seed=seed, difficulty=DIFFICULTIES[args.difficulty],
                    patterns=args.patterns, powerups=args.powerups)
    done = False
    clock = pygame.time.Clock()

    running = True
    frames_run = 0
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        mask = button_mask(pygame.key.get_pressed())
        if done:
            # The last frame stays up until the player asks for another game.
            if mask & RESTART:
                engine.reset(secrets.randbelow(2**31 - 1))
                done = False
        else:
            done = engine.step(action_for(mask))
        window.show(engine.frame())
        clock.tick(60)

        frames_run += 1
        if args.frames is not None and frames_run >= args.frames:
            running = False

    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
