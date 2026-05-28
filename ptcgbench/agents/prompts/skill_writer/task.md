**Deck**: {{ deck_name }}
**Result**: {{ result }}
**Turn count**: {{ turn_count }}

### Lessons learned
{% for lesson in lessons %}
- {{ lesson.lesson }}
{% if lesson.card_names %}  - Cards: {{ lesson.card_names | join(", ") }}
{% endif %}
{%- endfor %}

### Heuristics
{% for h in heuristics %}
- {{ h.heuristic }}
{% if h.card_names %}  - Cards: {{ h.card_names | join(", ") }}
{% endif %}
{%- endfor %}
