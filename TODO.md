- [x] Add User agent property https://github.com/NotJoeMartinez/yt-fts/blob/7fbc0088f30672b6fbfe2ea7351fa42bafe1f886/src/yt_fts/download/download_handler.py#L562  
My suggestion for your next Cursor prompt:

"Refine my ingest.py by incorporating two features from ytb-fts:

Add a list of 10 common User-Agents and have yt_dlp pick one at random for each request.

Update the channel sync to check both the /videos and /streams tabs of the channel URL so I don't miss any content."
- [ ] Impersonate the api calls
- [ ] Add the error handling during download and added error download to the registry database
- [ ] Create per channel per db file, and figure out data management for tables