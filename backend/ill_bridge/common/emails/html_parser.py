from html.parser import HTMLParser
from typing import ClassVar


class EmailHTMLSanitizer(HTMLParser):
    # Tags that are completely banned in strict emails

    BANNED_TAGS: ClassVar[frozenset[str]] = frozenset(
        {
            "script",
            "iframe",
            "object",
            "embed",
            "form",
            "input",
            "textarea",
        }
    )
    # Attributes that can execute JS or are malicious
    BANNED_ATTR_PREFIXES: ClassVar[tuple[str, ...]] = ("on", "javascript:")

    def __init__(self):
        super().__init__()
        self.result = []

    def handle_starttag(self, tag, attrs):
        tag_lower = tag.lower()
        if tag_lower in self.BANNED_TAGS:
            return

        # Filter out dangerous attributes
        clean_attrs = []
        for attr, value in attrs:
            attr_lower = attr.lower()
            if any(
                attr_lower.startswith(prefix) for prefix in self.BANNED_ATTR_PREFIXES
            ):
                continue
            if value and any(
                val_part.strip().lower().startswith("javascript:")
                for val_part in value.split()
            ):
                continue
            clean_attrs.append((attr, value))

        # Reconstruct the safe tag
        attr_str = "".join(
            f' {k}="{v}"' if v is not None else f" {k}" for k, v in clean_attrs
        )
        self.result.append(f"<{tag_lower}{attr_str}>")

    def handle_endtag(self, tag):
        if tag.lower() not in self.BANNED_TAGS:
            self.result.append(f"</{tag.lower()}>")

    def handle_data(self, data):
        self.result.append(data)

    def handle_entityref(self, name):
        self.result.append(f"&{name};")

    def handle_charref(self, name):
        self.result.append(f"&#{name};")

    @classmethod
    def clean(cls, html_content: str) -> str:
        parser = cls()
        parser.feed(html_content)
        return "".join(parser.result)
