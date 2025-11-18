import pytest
from unittest.mock import MagicMock, patch
from wrestling_logger.doc import create_google_doc, write_doc_content
from googleapiclient.errors import HttpError

@patch("wrestling_logger.doc.build")
def test_create_google_doc_success(mock_build):
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_service.files.return_value.create.return_value.execute.return_value = {"id": "doc123"}
    
    creds = MagicMock()
    doc_id = create_google_doc("My Doc", creds)
    
    assert doc_id == "doc123"
    mock_service.files.return_value.create.assert_called_once()

@patch("wrestling_logger.doc.build")
def test_write_doc_content_success(mock_build):
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    
    creds = MagicMock()
    write_doc_content("doc123", "content", creds)
    
    mock_service.documents.return_value.batchUpdate.assert_called_once()

@patch("wrestling_logger.doc.build")
def test_create_google_doc_failure(mock_build):
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    
    # Create a proper HttpError mock
    resp = MagicMock()
    resp.status = 500
    mock_service.files.return_value.create.return_value.execute.side_effect = HttpError(resp, b'{"error": "fail"}')
    
    creds = MagicMock()
    with pytest.raises(RuntimeError, match="Unable to create Google Doc"):
        create_google_doc("My Doc", creds)
