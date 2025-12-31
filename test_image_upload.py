#!/usr/bin/env python3
"""
Test script to verify image upload functionality.
Run this to test image downloading and uploading without the full sync process.
"""

import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from izzy_uploader.config import ServiceConfig
from izzy_uploader.client import IzzyleaseClient
from izzy_uploader.state import ImageStateStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
LOGGER = logging.getLogger(__name__)

def test_image_upload():
    """Test image upload functionality."""
    try:
        # Load config
        config = ServiceConfig.from_env()
        LOGGER.info(f"Config loaded. Image state file: {config.image_state_file}")

        # Create client and image store
        client = IzzyleaseClient(config)
        image_store = ImageStateStore(config.image_state_file)

        LOGGER.info("Client and image store initialized")

        # Test with a known car_id (you'll need to provide one)
        test_car_id = input("Enter a car_id to test image upload: ").strip()
        if not test_car_id:
            LOGGER.error("No car_id provided")
            return

        # Test image URL
        test_url = "https://carapi.activemotors.pl/photo/1889113/d0d5e6b6d4d6d06b.jpg"

        LOGGER.info(f"Testing image download and upload for car_id: {test_car_id}")
        LOGGER.info(f"Test URL: {test_url}")

        # Download image
        import urllib.request
        LOGGER.info("Downloading image...")
        with urllib.request.urlopen(test_url, timeout=30) as response:
            image_data = response.read()
            content_type = response.headers.get('Content-Type', 'image/jpeg')
            filename = test_url.split('/')[-1] or 'image.jpg'

        LOGGER.info(f"Downloaded {len(image_data)} bytes, content-type: {content_type}")

        # Upload image
        LOGGER.info("Uploading image...")
        image_id = client.upload_car_image(test_car_id, image_data, content_type=content_type, filename=filename)

        LOGGER.info(f"Upload successful! Image ID: {image_id}")

        # Store in image state
        image_store.add_image(test_car_id, image_id)
        image_store.save()

        LOGGER.info("Image stored in state file")

    except Exception as e:
        LOGGER.exception(f"Test failed: {e}")

if __name__ == "__main__":
    test_image_upload()
