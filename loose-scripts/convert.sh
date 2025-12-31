for file in *.opus; do
  ffmpeg -i "$file" -c:a libmp3lame -q:a 10 "${file%.opus}.mp3"
  echo "$file is moving to MP3 dir"
  mv "$file" '../Blinkist SiteRip Audio Collection (August 2023) (MP3)'
done
