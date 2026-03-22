---
title: Publications
layout: page
permalink: /publications.html
---

{% include feature/jumbotron.html %}

## Publications

This page includes publication entries drawn from collection metadata. If you have specific publications you want to list, paste them in manually or ask me to format a custom list.

{% assign publications = site.data.ihl-metadata | where_exp: 'item', 'item.publisher and item.publisher != ""' | uniq | slice: 0, 12 %}

{% if publications and publications.size > 0 %}
<p>Showing up to {{ publications.size }} publications extracted from object metadata:</p>
<ul>
  {% for item in publications %}
    <li>
      <strong>{{ item.title | default: item["title"] }}</strong>
      {% if item.author %} by {{ item.author }}{% endif %}
      {% if item.publisher %} ({{ item.publisher }}{% if item.publication_date_messy %}, {{ item.publication_date_messy }}{% endif %}){% endif %}
    </li>
  {% endfor %}
</ul>
{% else %}
<p>No publication metadata found in <code>_data/ihl-metadata.csv</code>.</p>
{% endif %}

## Add manual records

Add custom entries below if you want a curated publication list independent of object records:

- Example: “Lavenberg, I. (2001). Japanese Hanga: History and Aesthetics. UO Press.”

