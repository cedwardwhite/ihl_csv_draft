---
title: Publications
layout: page
permalink: /publications.html
---

# Publications

Selected publications referencing works or artists in this collection.

{% assign publications = site.data.publications %}
{% for p in publications %}
### {{ p.title }} ({{ p.year }})

**Authors:** {{ p.authors }}

{{ p.description }}

**Related Artists:**
{% assign artist_ids = p.related_artists | split: ";" %}
{% for aid in artist_ids %}
[{{ aid | strip }}]({{ '/artists/' | append: aid | strip | append: ".html" | relative_url }}){% unless forloop.last %}, {% endunless %}
{% endfor %}

**Related Objects:**
{% assign object_ids = p.related_objects | split: ";" %}
{% for oid in object_ids %}
[{{ oid | strip }}]({{ '/items/' | append: oid | strip | append: ".html" | relative_url }}){% unless forloop.last %}, {% endunless %}
{% endfor %}

[View Publication]({{ p.link }}){:target="_blank"}

---
{% endfor %}
