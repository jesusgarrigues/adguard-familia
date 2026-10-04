import io, socket, ssl, unittest, urllib.error
from unittest.mock import patch
import test_app
import app

class DiagnosticTests(unittest.TestCase):
    def setUp(self): app.DIAGNOSTICS.clear()
    def test_timeout_is_visible_without_credentials(self):
        with patch('urllib.request.urlopen',side_effect=urllib.error.URLError(socket.timeout('secret leak'))):
            with self.assertRaises(app.AdGuardError) as caught:
                app.api('status',config={'url':'http://example','username':'admin','password':'private','demo':False})
        self.assertEqual(caught.exception.detail['category'],'timeout')
        self.assertNotIn('private',str(list(app.DIAGNOSTICS)))
        self.assertNotIn('secret leak',str(list(app.DIAGNOSTICS)))
    def test_http_authentication_and_endpoint(self):
        err=app.network_error('clients',urllib.error.HTTPError('http://example',401,'private',{},None))
        self.assertEqual(err.detail['http_status'],401)
        self.assertEqual(err.detail['endpoint'],'clients')
        self.assertNotIn('private',str(err))
    def test_control_url_not_duplicated(self):
        response=io.BytesIO(b'{"version":"test"}')
        with patch('urllib.request.urlopen',return_value=response) as request:
            app.api('status',config={'url':'http://example/control/','username':'admin','password':'private','demo':False})
        self.assertEqual(request.call_args.args[0].full_url,'http://example/control/status')
    def test_html_response_is_visible(self):
        with patch('urllib.request.urlopen',return_value=io.BytesIO(b'<html>Login</html>')):
            with self.assertRaises(app.AdGuardError) as caught:
                app.api('status',config={'url':'http://example','username':'admin','password':'private','demo':False})
        self.assertEqual(caught.exception.detail['category'],'response')
    def test_broken_pipe_does_not_raise(self):
        handler=object.__new__(app.Handler)
        handler.send_response=lambda code:None
        handler.send_header=lambda *args:None
        handler.end_headers=lambda:None
        handler.wfile=unittest.mock.Mock()
        handler.wfile.write.side_effect=BrokenPipeError()
        handler.respond(502,{'error':'timeout'})

    def test_validation_response_is_explained_without_credentials(self):
        error=urllib.error.HTTPError('http://example/control/clients/update',400,'Bad Request',{},io.BytesIO(b'{"message":"Invalid schedule private-password"}'))
        result=app.network_error('clients/update',error,{'password':'private-password'})
        self.assertIn('Invalid schedule',str(result))
        self.assertNotIn('private-password',str(result))
        self.assertEqual(result.detail['http_status'],400)

if __name__=='__main__':unittest.main()
