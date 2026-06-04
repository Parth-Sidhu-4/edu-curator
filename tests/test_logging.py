import logging
import os
from edu_curator.logging import setup_logging

def test_setup_logging_defaults():
    # Run setup
    setup_logging(level="INFO")
    
    root_logger = logging.getLogger()
    assert root_logger.level == logging.INFO
    assert len(root_logger.handlers) >= 1
    
    # Check that third-party loggers are silenced
    assert logging.getLogger("urllib3").level == logging.WARNING
    assert logging.getLogger("openai").level == logging.WARNING

def test_setup_logging_custom_level(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    setup_logging()
    
    root_logger = logging.getLogger()
    assert root_logger.level == logging.DEBUG
