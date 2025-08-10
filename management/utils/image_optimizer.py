"""
Оптимизация изображений и управление медиа файлами
"""

import hashlib
import logging
import os
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageOps

from config.settings import MAX_FILE_SIZE, get_media_path

logger = logging.getLogger(__name__)


class ImageOptimizer:
    """Оптимизатор изображений"""

    def __init__(self):
        self.media_path = get_media_path()
        self.supported_formats = {".jpg", ".jpeg", ".png", ".webp"}
        self.quality_settings = {
            "high": {"quality": 95, "optimize": True},
            "medium": {"quality": 85, "optimize": True},
            "low": {"quality": 75, "optimize": True},
        }

    def optimize_image(
        self,
        input_path: str,
        output_path: str,
        quality: str = "medium",
        max_width: Optional[int] = None,
        max_height: Optional[int] = None,
    ) -> bool:
        """Оптимизирует изображение"""
        try:
            # Открываем изображение
            with Image.open(input_path) as img:
                # Конвертируем в RGB если нужно
                if img.mode in ("RGBA", "LA", "P"):
                    img = img.convert("RGB")

                # Изменяем размер если указаны ограничения
                if max_width or max_height:
                    img = self._resize_image(img, max_width, max_height)

                # Получаем настройки качества
                quality_settings = self.quality_settings.get(
                    quality, self.quality_settings["medium"]
                )

                # Определяем формат выходного файла
                output_format = Path(output_path).suffix.lower()
                if output_format == ".jpg":
                    output_format = "JPEG"
                elif output_format == ".png":
                    output_format = "PNG"
                elif output_format == ".webp":
                    output_format = "WEBP"
                else:
                    output_format = "JPEG"

                # Сохраняем оптимизированное изображение
                img.save(output_path, format=output_format, **quality_settings)

            logger.info(f"Изображение оптимизировано: {input_path} -> {output_path}")
            return True

        except Exception as e:
            logger.error(f"Ошибка при оптимизации изображения {input_path}: {e}")
            return False

    def _resize_image(
        self, img: Image.Image, max_width: Optional[int], max_height: Optional[int]
    ) -> Image.Image:
        """Изменяет размер изображения с сохранением пропорций"""
        if not max_width and not max_height:
            return img

        # Получаем текущие размеры
        current_width, current_height = img.size

        # Вычисляем новые размеры
        if max_width and max_height:
            # Ограничиваем по обоим параметрам
            ratio = min(max_width / current_width, max_height / current_height)
        elif max_width:
            # Ограничиваем только по ширине
            ratio = max_width / current_width
        else:
            # Ограничиваем только по высоте
            ratio = max_height / current_height

        # Применяем изменение размера только если нужно уменьшить
        if ratio < 1:
            new_width = int(current_width * ratio)
            new_height = int(current_height * ratio)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        return img

    def create_thumbnail(
        self, input_path: str, output_path: str, size: Tuple[int, int] = (200, 200)
    ) -> bool:
        """Создает миниатюру изображения"""
        try:
            with Image.open(input_path) as img:
                # Создаем миниатюру
                thumbnail = ImageOps.fit(img, size, Image.Resampling.LANCZOS)
                thumbnail.save(output_path, "JPEG", quality=85, optimize=True)

            logger.info(f"Создана миниатюра: {input_path} -> {output_path}")
            return True

        except Exception as e:
            logger.error(f"Ошибка при создании миниатюры {input_path}: {e}")
            return False

    def get_image_info(self, image_path: str) -> Optional[dict]:
        """Получает информацию об изображении"""
        try:
            with Image.open(image_path) as img:
                return {
                    "format": img.format,
                    "mode": img.mode,
                    "size": img.size,
                    "width": img.width,
                    "height": img.height,
                    "file_size": os.path.getsize(image_path),
                }
        except Exception as e:
            logger.error(
                f"Ошибка при получении информации об изображении {image_path}: {e}"
            )
            return None


class MediaManager:
    """Менеджер медиа файлов"""

    def __init__(self):
        self.media_path = get_media_path()
        self.image_optimizer = ImageOptimizer()
        self._initialized = False

    async def _async_init(self):
        """Асинхронная инициализация"""
        if self._initialized:
            return

        try:
            # Создаем необходимые директории
            self.media_path.mkdir(parents=True, exist_ok=True)
            (self.media_path / "lots").mkdir(exist_ok=True)
            (self.media_path / "temp").mkdir(exist_ok=True)

            # Проверяем доступность
            test_file = self.media_path / "temp" / ".test"
            test_file.touch()
            test_file.unlink()

            self._initialized = True
            logger.info("Медиа менеджер асинхронно инициализирован")

        except Exception as e:
            logger.error(f"Ошибка при асинхронной инициализации медиа менеджера: {e}")
            raise

    def is_initialized(self) -> bool:
        """Проверяет, инициализирован ли менеджер"""
        return self._initialized

    def organize_lot_media(self, lot_id: int, media_files: List[str]) -> dict:
        """Организует медиа файлы для лота"""
        lot_media_dir = self.media_path / "lots" / str(lot_id)
        lot_media_dir.mkdir(parents=True, exist_ok=True)

        organized_files = {"images": [], "files": [], "thumbnails": []}

        for file_path in media_files:
            try:
                file_path = Path(file_path)
                if not file_path.exists():
                    continue

                # Определяем тип файла
                if file_path.suffix.lower() in self.image_optimizer.supported_formats:
                    # Это изображение
                    image_info = self.image_optimizer.get_image_info(str(file_path))
                    if image_info:
                        # Копируем оригинал
                        original_path = (
                            lot_media_dir
                            / f"image_{len(organized_files['images']) + 1}{file_path.suffix}"
                        )
                        shutil.copy2(file_path, original_path)
                        organized_files["images"].append(str(original_path))

                        # Создаем миниатюру
                        thumbnail_path = (
                            lot_media_dir
                            / f"thumb_{len(organized_files['thumbnails']) + 1}.jpg"
                        )
                        if self.image_optimizer.create_thumbnail(
                            str(original_path), str(thumbnail_path)
                        ):
                            organized_files["thumbnails"].append(str(thumbnail_path))

                        # Оптимизируем для веб
                        web_path = (
                            lot_media_dir
                            / f"web_{len(organized_files['images']) + 1}.jpg"
                        )
                        if self.image_optimizer.optimize_image(
                            str(original_path),
                            str(web_path),
                            quality="medium",
                            max_width=1200,
                        ):
                            organized_files["images"].append(str(web_path))

                else:
                    # Это обычный файл
                    file_dest = lot_media_dir / "files" / file_path.name
                    file_dest.parent.mkdir(exist_ok=True)
                    shutil.copy2(file_path, file_dest)
                    organized_files["files"].append(str(file_dest))

            except Exception as e:
                logger.error(f"Ошибка при обработке файла {file_path}: {e}")

        return organized_files

    def cleanup_unused_media(self, lot_id: int):
        """Очищает неиспользуемые медиа файлы лота"""
        lot_media_dir = self.media_path / "lots" / str(lot_id)
        if lot_media_dir.exists():
            try:
                shutil.rmtree(lot_media_dir)
                logger.info(f"Очищены медиа файлы лота {lot_id}")
            except Exception as e:
                logger.error(f"Ошибка при очистке медиа файлов лота {lot_id}: {e}")

    def get_media_stats(self) -> dict:
        """Получает статистику медиа файлов"""
        try:
            total_size = 0
            file_count = 0
            image_count = 0

            for lot_dir in (self.media_path / "lots").glob("*"):
                if lot_dir.is_dir():
                    for file_path in lot_dir.rglob("*"):
                        if file_path.is_file():
                            file_count += 1
                            total_size += file_path.stat().st_size

                            if (
                                file_path.suffix.lower()
                                in self.image_optimizer.supported_formats
                            ):
                                image_count += 1

            return {
                "total_files": file_count,
                "total_images": image_count,
                "total_size_mb": total_size / (1024 * 1024),
                "media_path": str(self.media_path),
            }

        except Exception as e:
            logger.error(f"Ошибка при получении статистики медиа: {e}")
            return {}

    def validate_media_file(self, file_path: str) -> Tuple[bool, str]:
        """Проверяет валидность медиа файла"""
        try:
            file_path = Path(file_path)

            # Проверяем существование
            if not file_path.exists():
                return False, "Файл не существует"

            # Проверяем размер
            file_size = file_path.stat().st_size
            if file_size > MAX_FILE_SIZE * 1024 * 1024:  # Конвертируем в байты
                return (
                    False,
                    f"Файл слишком большой ({file_size / (1024 * 1024):.1f}MB > {MAX_FILE_SIZE}MB)",
                )

            # Проверяем расширение
            if file_path.suffix.lower() not in {
                ".jpg",
                ".jpeg",
                ".png",
                ".gif",
                ".webp",
                ".pdf",
                ".doc",
                ".docx",
                ".txt",
            }:
                return False, f"Неподдерживаемый формат файла: {file_path.suffix}"

            # Проверяем изображения
            if file_path.suffix.lower() in self.image_optimizer.supported_formats:
                try:
                    with Image.open(file_path) as img:
                        img.verify()
                except Exception:
                    return False, "Поврежденное изображение"

            return True, "Файл валиден"

        except Exception as e:
            return False, f"Ошибка валидации: {e}"

    def generate_file_hash(self, file_path: str) -> Optional[str]:
        """Генерирует хеш файла для проверки целостности"""
        try:
            hash_md5 = hashlib.md5()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            logger.error(f"Ошибка при генерации хеша файла {file_path}: {e}")
            return None


# Глобальные экземпляры
media_manager = MediaManager()
image_optimizer = ImageOptimizer()


def optimize_lot_images(lot_id: int, quality: str = "medium") -> bool:
    """Оптимизирует все изображения лота"""
    try:
        lot_media_dir = media_manager.media_path / "lots" / str(lot_id)
        if not lot_media_dir.exists():
            return False

        success_count = 0
        total_count = 0

        for image_file in lot_media_dir.glob("image_*"):
            if image_file.suffix.lower() in image_optimizer.supported_formats:
                total_count += 1
                optimized_path = image_file.parent / f"opt_{image_file.name}"

                if image_optimizer.optimize_image(
                    str(image_file), str(optimized_path), quality
                ):
                    success_count += 1

        logger.info(
            f"Оптимизировано {success_count}/{total_count} изображений лота {lot_id}"
        )
        return success_count > 0

    except Exception as e:
        logger.error(f"Ошибка при оптимизации изображений лота {lot_id}: {e}")
        return False


def get_media_usage_stats() -> dict:
    """Возвращает статистику использования медиа"""
    return media_manager.get_media_stats()
