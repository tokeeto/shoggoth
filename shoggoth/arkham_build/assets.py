import hashlib
import re
import shutil
from html import escape

from shoggoth.files import overlay_dir
from shoggoth.renderer.richtext.tags import parse_tag_attributes

_IMAGE_TAG_PATTERN = re.compile(r"<image(?=\s|>)", re.IGNORECASE)


class ImageAssetExporter:
    def __init__(self, project, adapter):
        self.project = project
        self.adapter = adapter
        self._urls_by_path = {}

    def export(self, source):
        if not self.adapter.images_enabled or not source:
            return None

        path = self.project.find_file(source)
        if path is None:
            path = overlay_dir / source

        if not path.is_file():
            return None

        path = path.resolve()
        if path in self._urls_by_path:
            return self._urls_by_path[path]

        with path.open("rb") as image:
            digest = hashlib.file_digest(image, "sha256").hexdigest()

        filename = f"assets/{digest}{path.suffix}"
        destination = self.adapter.export_file(filename)
        if not destination.exists():
            shutil.copyfile(path, destination)

        url = self.adapter.image_url(filename)
        self._urls_by_path[path] = url
        return url

    def map_tag(self, tag):
        if _IMAGE_TAG_PATTERN.match(tag) is None:
            return None

        attributes = {
            key.lower(): value for key, value in parse_tag_attributes(tag).items()
        }

        url = self.export(attributes.get("src"))
        if url is None:
            return ""

        return (
            f'<img src="{escape(url, quote=True)}" '
            'style="height:1em;vertical-align:middle">'
        )
