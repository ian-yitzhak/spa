"""Strip anything dangerous from vendor-supplied rich text (CKEditor) before it is stored or rendered."""
import nh3

ALLOWED_TAGS = {"p", "br", "strong", "b", "em", "i", "u", "s", "a", "ul", "ol", "li", "h3", "h4", "blockquote"}
ALLOWED_ATTRS = {"a": {"href", "title", "target"}}


def clean_html(value):
    if not value:
        return value
    return nh3.clean(value, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, link_rel="nofollow noopener", url_schemes={"http", "https", "mailto", "tel"})
