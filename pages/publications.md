---
title: Publications
layout: page
permalink: /publications.html
---

# Publications

Selected publications referencing works or artists in this collection.

{% assign publications = site.data.publications %}
{% for p in publications %}
---

### {{ p.title }} ({{ p.year }})

**Authors:** {{ p.authors }}

{{ p.description }}

<div style="display: flex; flex-wrap: wrap; gap: 2rem; margin-top: 0.5em;">
  <div style="flex: 1 1 200px;">
    <strong>Related Artists:</strong><br>
    {% assign artist_ids = p.related_artists | split: ";" %}
    {% for aid in artist_ids %}
    <a href="{{ '/artists/' | append: aid | strip | append: '.html' | relative_url }}">{{ aid | strip }}</a>{% unless forloop.last %}, {% endunless %}
    {% endfor %}
  </div>
  <div style="flex: 1 1 200px;">
    <strong>Related Objects:</strong><br>
    {% assign object_ids = p.related_objects | split: ";" %}
    {% for oid in object_ids %}
    <a href="{{ '/items/' | append: oid | strip | append: '.html' | relative_url }}">{{ oid | strip }}</a>{% unless forloop.last %}, {% endunless %}
    {% endfor %}
  </div>
</div>

<p><a href="{{ p.link }}" target="_blank">View Publication</a></p>

{% endfor %}
