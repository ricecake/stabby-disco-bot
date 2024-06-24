import unittest

from stabby import text_utils
from tests.helpers import with_params


class TestTextUtils(unittest.TestCase):

    @with_params('Prompt test cases', [
        ('test', 'Test', ''),
        ('test the thing', 'Test The Thing', ''),
        ('test               thing', 'Test Thing', ''),
        ('test the thing, other thing', 'Test The Thing', 'Other thing'),
        ('test the thing, other thing, yet again', 'Test The Thing', 'Other thing, Yet again'),
        ('foo, bar, baz', 'Foo', 'Bar, Baz'),
        ('TEST THING, OTHER THING, YET AGAIN', 'Test The Thing', 'Other thing', 'Yet again'),
    ])
    def test_gen_description(self, prompt, title, description):
        got_title, got_description = text_utils.prompt_to_overlay(prompt)
        self.assertEqual(got_title, title)
        self.assertEqual(got_description, description)
