@echo off
curl -X POST "https://xcbeoylnpxqytjpytwdq.supabase.co/auth/v1/token?grant_type=password" -H "apikey: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhjYmVveWxucHhxeXRqcHl0d2RxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzg4NDk1OTQsImV4cCI6MjA5NDQyNTU5NH0.paMUZJTquUZ21ujMcnSwzpB95D7XybFo6ZQP71CagwA" -H "Content-Type: application/json" -d "{\"email\": \"mahomedabubakr84@gmail.com\", \"password\": \"AbuBakr1\"}" -o token_response.json
echo.
echo Login response saved to token_response.json