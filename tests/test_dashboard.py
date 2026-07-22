import unittest

from app.dashboard import render_dashboard


class DashboardTests(unittest.TestCase):
    def test_renders_owned_records_conflicts_and_error(self):
        html = render_dashboard(
            ownership={'app.home.prettybaked.com': 'docker-swarm.local'},
            conflicts={'dup.home.prettybaked.com'},
            last_error='UniFi said <nope>',
        )

        self.assertIn('<td>app.home.prettybaked.com</td>', html)
        self.assertIn('<td>docker-swarm.local</td>', html)
        self.assertIn('dup.home.prettybaked.com', html)
        self.assertIn('UniFi said &lt;nope&gt;', html)

    def test_renders_empty_state(self):
        html = render_dashboard(ownership={}, conflicts=set(), last_error=None)

        self.assertIn('No controller-owned records', html)
        self.assertIn('<code>None</code>', html)


if __name__ == '__main__':
    unittest.main()
