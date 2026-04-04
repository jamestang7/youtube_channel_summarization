 from youtube_rag.main import main
 
 
 def test_main_returns_ready_message() -> None:
     assert "ready" in main()
