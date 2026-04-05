- [x] Add User agent property https://github.com/NotJoeMartinez/yt-fts/blob/7fbc0088f30672b6fbfe2ea7351fa42bafe1f886/src/yt_fts/download/download_handler.py#L562  
My suggestion for your next Cursor prompt:

"Refine my ingest.py by incorporating two features from ytb-fts:

Add a list of 10 common User-Agents and have yt_dlp pick one at random for each request.

Update the channel sync to check both the /videos and /streams tabs of the channel URL so I don't miss any content."
- [ ] Impersonate the api calls
- [x] Add the error handling during download and added error download to the registry database
- [ ] Create per channel per db file, and figure out data management for tables
- [X] Set LLM_PROVIDER=ollama in config 
- [x] Update the title time information in cards like this 发布时间: 04/02/2026
- [ ] Ask user and confirm the config of model usage in transcribeing, preprocessing cleaning text, summarizing and answering questions, chunking embedding choice and change the code base accodingly 
- [x] sync channel Trade-off
- [x] elegant cli design