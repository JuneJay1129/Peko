"""
用 pygame 播放放大后的动画（测试用）
用法: python scripts/test_animation.py
"""
import pygame
import sys
import os

# 确保从项目根目录运行
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)


def animate_sprites_with_scaling(frames, scale_factor=1, frame_rate=10):
    """
    用 pygame 播放放大后的动画。
    :param frames: 单帧图片路径列表
    :param scale_factor: 放大倍数
    :param frame_rate: 帧率 (帧/秒)
    """
    pygame.init()
    first_image = pygame.image.load(frames[0])
    frame_width = first_image.get_width() * scale_factor
    frame_height = first_image.get_height() * scale_factor

    screen = pygame.display.set_mode((frame_width, frame_height))
    pygame.display.set_caption("Desktop Pet Animation")

    images = [
        pygame.transform.scale(pygame.image.load(frame), (frame_width, frame_height))
        for frame in frames
    ]
    clock = pygame.time.Clock()
    running = True
    frame_index = 0

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        screen.fill((255, 255, 255))
        screen.blit(images[frame_index], (0, 0))
        pygame.display.flip()

        frame_index = (frame_index + 1) % len(images)
        clock.tick(frame_rate)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    # 使用某宠物的 resource（如 neko）
    frame_paths = [
        "pets/neko/resource/stand/0.png",
        "pets/neko/resource/stand/1.png",
    ]
    animate_sprites_with_scaling(frame_paths, scale_factor=30, frame_rate=2)
