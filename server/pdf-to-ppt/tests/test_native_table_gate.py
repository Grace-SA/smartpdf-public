"""Native tables must not bypass repair with values assigned to the wrong rows."""
import pytest
from pptx import Presentation
from pptx.util import Pt

from smartppt.assisted import safe_table


def table_slide(values):
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    table = slide.shapes.add_table(2, 2, Pt(10), Pt(10), Pt(300), Pt(60)).table
    for cell, value in zip((c for row in table.rows for c in row.cells), values):
        cell.text = value
    return slide


@pytest.mark.parametrize('values', [
    ['Revenue', '200', 'Expense', '100'],
    ['Expense', '100', 'Revenue', '200'],
    ['100', 'Revenue', '200', 'Expense'],
])
def test_swapped_table_content_cannot_bypass_coordinate_validation(values):
    slide = table_slide(values)
    assert not safe_table(slide, 'Revenue 100\nExpense 200')


def test_ordered_table_content_is_retained_with_normalized_whitespace():
    slide = table_slide(['Revenue', '100', 'Expense', '200'])
    assert safe_table(slide, 'Revenue\t１００\r\nExpense 200')


def test_long_table_cannot_hide_a_value_swap_below_similarity_threshold():
    label = 'Account description ' * 300
    slide = table_slide([label, '200', 'Expense', '100'])
    assert not safe_table(slide, label + '100\nExpense 200')
