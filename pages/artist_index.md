---
title: Artist Index
layout: page
permalink: /artist_index.html
---

# Artist Index

List of artists represented in the collection.

Artist Listing (family name precedes given name)

{% assign artists = site.data.artist-metadata %}
{% for a in artists %}
- [{{ a.title }}]({{ '/artists/' | append: a.objectid | append: ".html" | relative_url }}) ({{ a.date }}){% endfor %}
