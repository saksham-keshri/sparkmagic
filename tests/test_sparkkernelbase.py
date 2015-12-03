from nose.tools import with_setup
from mock import MagicMock, call

from remotespark.sparkkernelbase import SparkKernelBase
from remotespark.livyclientlib.utils import get_connection_string
from remotespark.livyclientlib.configuration import _t_config_hook


kernel = None
user_ev = "USER"
pass_ev = "PASS"
url_ev = "URL"
send_error_mock = None
execute_cell_mock = None
do_shutdown_mock = None


class TestSparkKernel(SparkKernelBase):
    client_name = "TestKernel"


def _setup():
    global kernel, user_ev, pass_ev, url_ev, send_error_mock, execute_cell_mock, do_shutdown_mock

    kernel = TestSparkKernel()
    kernel.use_auto_viz = False
    kernel.username_conf_name = user_ev
    kernel.password_conf_name = pass_ev
    kernel.url_conf_name = url_ev
    kernel.session_language = "python"

    kernel._ipython_send_error = send_error_mock = MagicMock()
    kernel._execute_cell_for_user = execute_cell_mock = MagicMock()
    kernel._do_shutdown_ipykernel = do_shutdown_mock = MagicMock()


def _teardown():
    _t_config_hook({})


@with_setup(_setup, _teardown)
def test_get_config():
    usr = "u"
    pwd = "p"
    url = "url"

    config = {user_ev: usr, pass_ev: pwd, url_ev: url}
    _t_config_hook(config)

    u, p, r = kernel._get_configuration()

    assert u == usr
    assert p == pwd
    assert r == url


@with_setup(_setup, _teardown)
def test_get_config_not_set():
    try:
        kernel._get_configuration()

        # Above should have thrown because env var not set
        assert False
    except ValueError:
        assert send_error_mock.call_count == 1


@with_setup(_setup, _teardown)
def test_initialize_magics():
    # Set up
    usr = "u"
    pwd = "p"
    url = "url"
    conn_str = get_connection_string(url, usr, pwd)

    # Call method
    assert not kernel.already_ran_once
    kernel._initialize_magics(usr, pwd, url)

    # Assertions
    assert kernel.already_ran_once
    expected = [call("%spark add TestKernel python {} skip".format(conn_str), True, False, None, False),
                call("%load_ext remotespark", True, False, None, False)]
    for kall in expected:
        assert kall in execute_cell_mock.mock_calls


@with_setup(_setup, _teardown)
def test_do_execute_initializes_magics_if_not_run():
    # Set up
    usr = "u"
    pwd = "p"
    url = "url"
    conn_str = get_connection_string(url, usr, pwd)
    config_mock = MagicMock()
    config_mock.return_value = (usr, pwd, url)

    kernel._get_configuration = config_mock

    code = "code"

    # Call method
    assert not kernel.already_ran_once
    kernel.do_execute(code, False)

    # Assertions
    assert kernel.already_ran_once
    assert call("%spark add TestKernel python {} skip"
                .format(conn_str), True, False, None, False) in execute_cell_mock.mock_calls
    assert call("%load_ext remotespark", True, False, None, False) in execute_cell_mock.mock_calls
    assert call("%%spark\n{}".format(code), False, True, None, False) in execute_cell_mock.mock_calls


@with_setup(_setup, _teardown)
def test_call_spark():
    # Set up
    code = "some spark code"
    kernel.already_ran_once = True

    # Call method
    kernel.do_execute(code, False)

    # Assertions
    assert kernel.already_ran_once
    execute_cell_mock.assert_called_once_with("%%spark\n{}".format(code), False, True, None, False)


@with_setup(_setup, _teardown)
def test_execute_throws_if_fatal_error_happened():
    # Set up
    fatal_error = "Error."
    code = "some spark code"
    kernel._fatal_error = fatal_error

    # Call method
    try:
        kernel.do_execute(code, False)

        # Fail if not thrown
        assert False
    except ValueError:
        # Assertions
        assert kernel._fatal_error == fatal_error
        assert execute_cell_mock.call_count == 0
        assert send_error_mock.call_count == 1


@with_setup(_setup, _teardown)
def test_execute_throws_if_fatal_error_happens_for_execution():
    # Set up
    fatal_error = u"Error."
    message = "{}\nException details:\n\t\"{}\"".format(fatal_error, fatal_error)
    stream_content = {"name": "stderr", "text": kernel.fatal_error_suggestion.format(message)}
    code = "some spark code"
    reply_content = dict()
    reply_content[u"status"] = u"error"
    reply_content[u"evalue"] = fatal_error
    execute_cell_mock.return_value = reply_content

    # Call method
    try:
        kernel._execute_cell(code, False, shutdown_if_error=True, log_if_error=fatal_error)

        # Fail if not thrown
        assert False
    except ValueError:
        # Assertions
        assert kernel._fatal_error == message
        assert execute_cell_mock.call_count == 1
        send_error_mock.assert_called_once_with(stream_content)


@with_setup(_setup, _teardown)
def test_call_spark_sql_new_line():
    def _check(prepend):
        # Set up
        plain_code = "select tables"
        code = prepend + plain_code
        kernel.already_ran_once = True
        execute_cell_mock.reset_mock()

        # Call method
        kernel.do_execute(code, False)

        # Assertions
        assert kernel.already_ran_once
        execute_cell_mock.assert_called_once_with("%%spark -c sql\n{}".format(plain_code), False, True, None, False)

    _check("%sql ")
    _check("%sql\n")
    _check("%%sql ")
    _check("%%sql\n")


@with_setup(_setup, _teardown)
def test_call_spark_hive_new_line():
    def _check(prepend):
        # Set up
        plain_code = "select tables"
        code = prepend + plain_code
        kernel.already_ran_once = True
        execute_cell_mock.reset_mock()

        # Call method
        kernel.do_execute(code, False)

        # Assertions
        assert kernel.already_ran_once
        execute_cell_mock.assert_called_once_with("%%spark -c hive\n{}".format(plain_code), False, True, None, False)

    _check("%hive ")
    _check("%hive\n")
    _check("%%hive ")
    _check("%%hive\n")


@with_setup(_setup, _teardown)
def test_shutdown_cleans_up():
    # No restart
    kernel._execute_cell_for_user = ecfu_m = MagicMock()
    kernel._do_shutdown_ipykernel = dsi_m = MagicMock()
    kernel.already_ran_once = True

    kernel.do_shutdown(False)

    assert not kernel.already_ran_once
    ecfu_m.assert_called_once_with("%spark cleanup", True, False)
    dsi_m.assert_called_once_with(False)

    # On restart
    kernel._execute_cell_for_user = ecfu_m = MagicMock()
    kernel._do_shutdown_ipykernel = dsi_m = MagicMock()
    kernel.already_ran_once = True

    kernel.do_shutdown(True)

    assert not kernel.already_ran_once
    ecfu_m.assert_called_once_with("%spark cleanup", True, False)
    dsi_m.assert_called_once_with(True)
