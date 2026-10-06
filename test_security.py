import logging, unittest
import security


class SecurityTests(unittest.TestCase):
    def test_failure_log_has_type_and_location_but_no_message(self):
        def failing():
            raise RuntimeError('password=private-secret https://user:pw@adguard.local')
        with self.assertLogs(level='ERROR') as logs:
            try:
                failing()
            except RuntimeError:
                security.log_failure('POST /api/client')
        line = ''.join(logs.output)
        self.assertIn('RuntimeError', line)
        self.assertIn('test_security.py', line)
        self.assertIn('failing', line)
        self.assertNotIn('private-secret', line)
        self.assertNotIn('adguard.local', line)

    def test_csp_hashes_each_inline_script(self):
        policy = security.content_security_policy('<script src="/a.js"></script><script>run()</script>')
        self.assertIn("script-src 'self' 'sha256-", policy)
        self.assertEqual(policy.count("'sha256-"), 1)
        self.assertIn("frame-ancestors 'none'", policy)


if __name__ == '__main__':
    unittest.main()
