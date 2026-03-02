"""
分割精灵表为单帧图片
用法: python scripts/devide_frames.py
或在代码中: from scripts.devide_frames import split_sprite_sheet

输出到宠物 resource 时，使用 pets/<宠物id>/resource/<状态>/ 作为 output_dir，
例如: pets/neko/resource/stand/
"""
from PIL import Image
import os


def split_sprite_sheet(image_path, rows, cols, output_dir):
    """
    分割精灵表为单帧图片。
    :param image_path: 精灵表路径
    :param rows: 行数
    :param cols: 列数
    :param output_dir: 输出文件夹
    """
    img = Image.open(image_path)
    frame_width = img.width // cols
    frame_height = img.height // rows

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    frames = []
    for row in range(rows):
        for col in range(cols):
            left = col * frame_width
            top = row * frame_height
            right = left + frame_width
            bottom = top + frame_height
            frame = img.crop((left, top, right, bottom))
            frame_path = os.path.join(output_dir, f"frame_{row}_{col}.png")
            frame.save(frame_path)
            frames.append(frame_path)
    return frames
