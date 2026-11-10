from collections.abc import Iterable
from pathlib import Path

from PIL import Image

from shoggoth.arkham_build.cards import ImageTarget
from shoggoth.arkham_build.thumbnails import extract_thumbnail
from shoggoth.arkham_build.upload_adapters import UploadAdapter
from shoggoth.card import Card
from shoggoth.renderer.card_renderer import CardRenderer, renderer_for_card


def export_card_images(
    card: Card,
    targets: Iterable[ImageTarget],
    adapter: UploadAdapter,
    renderer: CardRenderer,
) -> None:
    renderer = renderer_for_card(renderer, card)

    for target in targets:
        filename = f"{card.id}{target.file_suffix}.webp"
        thumbnail_filename = f"{card.id}{target.file_suffix}_thumbnail.webp"

        with renderer.render_card_side(card, target.face, include_bleed=False) as image:
            _save_webp(image, adapter.export_file(filename))

            with extract_thumbnail(image, target.face, target.card_type) as thumbnail:
                _save_webp(thumbnail, adapter.export_file(thumbnail_filename))

        prefix = target.field_prefix
        record = target.record

        record[f"{prefix}image_url"] = adapter.image_url(filename)
        record[f"{prefix}thumbnail_url"] = adapter.image_url(thumbnail_filename)


def _save_webp(image: Image.Image, path: Path) -> None:
    image.save(path, format="WEBP", quality=80, method=6)
