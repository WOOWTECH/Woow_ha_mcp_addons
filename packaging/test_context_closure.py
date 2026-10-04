"""Offline .dockerignore semantics and real-repository closure. No Docker."""
from pathlib import Path
import unittest

import context_closure as c

ROOT = Path(__file__).resolve().parent.parent


class ContextClosureTests(unittest.TestCase):
    def test_moby_semantics(self):
        p = c.load_ignore('**\n!apps/\n**/node_modules\n!keep/*.py\n**/data\n')
        self.assertTrue(c.excluded(p, 'README.md'))
        # A re-included parent directory decides for its whole subtree.
        self.assertFalse(c.excluded(p, 'apps/n8n/metadata_reads.cjs'))
        self.assertTrue(c.excluded(p, 'apps/n8n/node_modules/x/index.js'))
        self.assertFalse(c.excluded(p, 'keep/a.py'))
        self.assertTrue(c.excluded(p, 'keep/sub/a.py'))  # single * never crosses '/'
        self.assertTrue(c.excluded(p, 'apps/x/data/state.json'))

    def test_dropped_or_untracked_copy_source_fails(self):
        dockerfile = 'FROM x AS a\nCOPY --from=a /x /y\nCOPY apps/n8n ./apps/n8n\nCOPY missing.txt ./\n'
        files = ['apps/n8n/run.py', 'apps/n8n/helper.cjs']
        found = c.problems(files, '**\n!apps/**/*.py\n', dockerfile)
        self.assertIn('COPY source excluded from context: apps/n8n/helper.cjs', found)
        self.assertIn('COPY source not tracked: missing.txt', found)
        self.assertNotIn('COPY source excluded from context: apps/n8n/run.py', found)
        self.assertEqual(c.copy_sources(dockerfile), ['apps/n8n', 'missing.txt'])

    def test_unsupported_syntax_is_rejected_not_undercounted(self):
        bad = {
            'dangling': 'COPY a \\\n',
            'json': 'COPY ["a", "./"]\n',
            'heredoc': 'COPY <<EOF /x\nhi\nEOF\n',
            'add': 'ADD a ./\n',
            'lowercase': 'copy a ./\n',
            'directive': '# syntax=docker/dockerfile:1\nCOPY a ./\n',
            'variable': 'COPY $SRC ./\n',
            'glob': 'COPY apps/*.py ./\n',
            'parents': 'COPY --parents a ./\n',
            'exclude': 'COPY --exclude=x a ./\n',
            'absolute': 'COPY /etc/passwd ./\n',
        }
        for name, dockerfile in bad.items():
            with self.subTest(name), self.assertRaises(ValueError):
                c.copy_sources(dockerfile)
        with self.assertRaises(ValueError):
            c.load_ignore('**\n![ab].py\n')
        self.assertEqual(c.copy_sources('COPY --chown=1:1 --link a b ./\n'), ['a', 'b'])
        joined = 'LABEL a=1 \\\n  b=2\nCOPY one \\\n# dropped comment\n  two ./dst\n'
        self.assertEqual(c.copy_sources(joined), ['one', 'two'])

    def test_repository_dockerfiles_are_closed(self):
        c.main(ROOT)


if __name__ == '__main__':
    unittest.main()
