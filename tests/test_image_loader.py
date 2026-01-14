#!/usr/bin/env python3
"""
Property-based tests for local image loader
Feature: ghcr-oci-support
"""

import unittest
import json
import os
import tempfile
import tarfile
import shutil
from unittest.mock import Mock, patch
from hypothesis import given, settings, strategies as st
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from android_docker.image_loader import LocalImageLoader


# Hypothesis strategies for generating test data
@st.composite
def docker_image_tar_strategy(draw, valid=True):
    """Generate Docker image tar structures"""
    # Generate random layer count
    num_layers = draw(st.integers(min_value=1, max_value=5))
    
    # Generate layer filenames
    layers = []
    for i in range(num_layers):
        layer_hash = draw(st.text(min_size=64, max_size=64, alphabet='0123456789abcdef'))
        layers.append(f"{layer_hash}/layer.tar")
    
    # Generate config filename
    config_hash = draw(st.text(min_size=64, max_size=64, alphabet='0123456789abcdef'))
    config_file = f"{config_hash}.json"
    
    # Generate repo tags
    image_name = draw(st.text(min_size=1, max_size=20, 
                             alphabet=st.characters(whitelist_categories=('Ll', 'Lu', 'Nd'), 
                                                   whitelist_characters='-_')))
    tag = draw(st.text(min_size=1, max_size=10,
                      alphabet=st.characters(whitelist_categories=('Ll', 'Lu', 'Nd'),
                                            whitelist_characters='.-_')))
    repo_tags = [f"{image_name}:{tag}"]
    
    # Create manifest
    manifest = [{
        "Config": config_file,
        "RepoTags": repo_tags,
        "Layers": layers
    }]
    
    if not valid:
        # Randomly corrupt the manifest
        corruption_type = draw(st.integers(min_value=0, max_value=3))
        if corruption_type == 0:
            # Remove Config
            del manifest[0]["Config"]
        elif corruption_type == 1:
            # Remove Layers
            del manifest[0]["Layers"]
        elif corruption_type == 2:
            # Empty layers
            manifest[0]["Layers"] = []
        elif corruption_type == 3:
            # Empty manifest
            manifest = []
    
    return {
        'manifest': manifest,
        'config_file': config_file,
        'layers': layers,
        'repo_tags': repo_tags
    }


def create_test_tar(tar_data, temp_dir):
    """Create a test tar file from tar_data"""
    tar_path = os.path.join(temp_dir, 'test_image.tar')
    
    with tarfile.open(tar_path, 'w') as tar:
        # Add manifest.json
        manifest_path = os.path.join(temp_dir, 'manifest.json')
        with open(manifest_path, 'w') as f:
            json.dump(tar_data['manifest'], f)
        tar.add(manifest_path, arcname='manifest.json')
        
        # Add config file
        if tar_data['manifest'] and 'Config' in tar_data['manifest'][0]:
            config_path = os.path.join(temp_dir, tar_data['config_file'])
            with open(config_path, 'w') as f:
                json.dump({'architecture': 'amd64', 'os': 'linux'}, f)
            tar.add(config_path, arcname=tar_data['config_file'])
        
        # Add layer files
        if tar_data['manifest'] and 'Layers' in tar_data['manifest'][0]:
            for layer in tar_data['layers']:
                layer_path = os.path.join(temp_dir, layer)
                os.makedirs(os.path.dirname(layer_path), exist_ok=True)
                # Create a small tar file for the layer
                with tarfile.open(layer_path, 'w') as layer_tar:
                    # Add a dummy file
                    dummy_file = os.path.join(temp_dir, 'dummy.txt')
                    with open(dummy_file, 'w') as f:
                        f.write('test')
                    layer_tar.add(dummy_file, arcname='dummy.txt')
                tar.add(layer_path, arcname=layer)
    
    return tar_path


class TestDockerImageTarValidation(unittest.TestCase):
    """
    Property 4: Docker Image Tar Validation
    Validates: Requirements 2.2, 2.5
    """
    
    @given(tar_data=docker_image_tar_strategy(valid=True))
    @settings(max_examples=100)
    def test_valid_tar_validation(self, tar_data):
        """
        Feature: ghcr-oci-support, Property 4: Docker Image Tar Validation
        
        For any tar archive with valid Docker image structure, the validation 
        function SHALL return true.
        """
        temp_dir = tempfile.mkdtemp()
        try:
            # Create test tar
            tar_path = create_test_tar(tar_data, temp_dir)
            
            # Create loader
            cache_dir = os.path.join(temp_dir, 'cache')
            loader = LocalImageLoader(cache_dir)
            
            # Validate
            is_valid, error_msg = loader._validate_tar_structure(tar_path)
            
            # Should be valid
            self.assertTrue(is_valid, 
                          f"Valid tar should pass validation. Error: {error_msg}")
            self.assertIsNone(error_msg, 
                            "Valid tar should not have error message")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    @given(tar_data=docker_image_tar_strategy(valid=False))
    @settings(max_examples=100)
    def test_invalid_tar_validation(self, tar_data):
        """
        Feature: ghcr-oci-support, Property 4: Docker Image Tar Validation
        
        For any tar archive with invalid Docker image structure, the validation 
        function SHALL return false with a descriptive error message.
        """
        temp_dir = tempfile.mkdtemp()
        try:
            # Create test tar
            tar_path = create_test_tar(tar_data, temp_dir)
            
            # Create loader
            cache_dir = os.path.join(temp_dir, 'cache')
            loader = LocalImageLoader(cache_dir)
            
            # Validate
            is_valid, error_msg = loader._validate_tar_structure(tar_path)
            
            # Should be invalid
            self.assertFalse(is_valid,
                           "Invalid tar should fail validation")
            self.assertIsNotNone(error_msg,
                               "Invalid tar should have error message")
            self.assertGreater(len(error_msg), 0,
                             "Error message should not be empty")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestImageLoadExtraction(unittest.TestCase):
    """
    Property 5: Image Load Extraction Correctness
    Validates: Requirements 2.1, 2.3
    """
    
    @given(tar_data=docker_image_tar_strategy(valid=True))
    @settings(max_examples=50)  # Reduced for performance
    def test_image_load_extraction_correctness(self, tar_data):
        """
        Feature: ghcr-oci-support, Property 5: Image Load Extraction Correctness
        
        For any valid Docker image tar archive, loading it SHALL result in a 
        cached tar file in the cache directory with a name derived from the 
        image name and a hash.
        """
        temp_dir = tempfile.mkdtemp()
        try:
            # Create test tar
            tar_path = create_test_tar(tar_data, temp_dir)
            
            # Create loader
            cache_dir = os.path.join(temp_dir, 'cache')
            loader = LocalImageLoader(cache_dir)
            
            # Load image
            success, image_name, error_msg = loader.load_image(tar_path)
            
            # Should succeed
            self.assertTrue(success, f"Load should succeed. Error: {error_msg}")
            self.assertIsNotNone(image_name, "Image name should not be None")
            
            # Check cache directory
            cache_files = os.listdir(cache_dir)
            
            # Should have at least one file (the cached tar)
            self.assertGreater(len(cache_files), 0,
                             "Cache directory should contain files")
            
            # Find the cached tar file (not .info file)
            tar_files = [f for f in cache_files if not f.endswith('.info')]
            self.assertGreater(len(tar_files), 0,
                             "Should have at least one cached tar file")
            
            # Verify the cached file exists and is readable
            cached_tar = os.path.join(cache_dir, tar_files[0])
            self.assertTrue(os.path.exists(cached_tar),
                          "Cached tar file should exist")
            self.assertGreater(os.path.getsize(cached_tar), 0,
                             "Cached tar file should not be empty")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestImageRegistration(unittest.TestCase):
    """
    Property 6: Image Registration After Load
    Validates: Requirements 2.4
    """
    
    @given(tar_data=docker_image_tar_strategy(valid=True))
    @settings(max_examples=50)  # Reduced for performance
    def test_image_registration_after_load(self, tar_data):
        """
        Feature: ghcr-oci-support, Property 6: Image Registration After Load
        
        For any successfully loaded image, querying the image list immediately 
        after loading SHALL return an entry for that image with correct metadata.
        """
        temp_dir = tempfile.mkdtemp()
        try:
            # Create test tar
            tar_path = create_test_tar(tar_data, temp_dir)
            
            # Create loader
            cache_dir = os.path.join(temp_dir, 'cache')
            loader = LocalImageLoader(cache_dir)
            
            # Load image
            success, image_name, error_msg = loader.load_image(tar_path)
            
            # Should succeed
            self.assertTrue(success, f"Load should succeed. Error: {error_msg}")
            
            # Check for .info file
            cache_files = os.listdir(cache_dir)
            info_files = [f for f in cache_files if f.endswith('.info')]
            
            self.assertGreater(len(info_files), 0,
                             "Should have at least one .info file")
            
            # Read and verify info file
            info_path = os.path.join(cache_dir, info_files[0])
            with open(info_path, 'r') as f:
                info_data = json.load(f)
            
            # Verify required fields
            self.assertIn('image_url', info_data,
                         "Info should contain image_url")
            self.assertIn('cache_path', info_data,
                         "Info should contain cache_path")
            self.assertIn('created_time', info_data,
                         "Info should contain created_time")
            self.assertIn('source', info_data,
                         "Info should contain source")
            
            # Verify source is 'local'
            self.assertEqual(info_data['source'], 'local',
                           "Source should be 'local' for loaded images")
            
            # Verify image_url matches
            self.assertEqual(info_data['image_url'], image_name,
                           "Image URL in info should match loaded image name")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestImageLoadIdempotence(unittest.TestCase):
    """
    Property 7: Image Load Idempotence
    Validates: Requirements 2.6
    """
    
    @given(tar_data=docker_image_tar_strategy(valid=True))
    @settings(max_examples=50)  # Reduced for performance
    def test_image_load_idempotence(self, tar_data):
        """
        Feature: ghcr-oci-support, Property 7: Image Load Idempotence
        
        For any valid Docker image tar, loading it twice SHALL result in the 
        same cached image (updated timestamp but same content), not duplicate entries.
        """
        temp_dir = tempfile.mkdtemp()
        try:
            # Create test tar
            tar_path = create_test_tar(tar_data, temp_dir)
            
            # Create loader
            cache_dir = os.path.join(temp_dir, 'cache')
            loader = LocalImageLoader(cache_dir)
            
            # Load image first time
            success1, image_name1, error_msg1 = loader.load_image(tar_path)
            self.assertTrue(success1, f"First load should succeed. Error: {error_msg1}")
            
            # Get cache state after first load
            cache_files_1 = set(os.listdir(cache_dir))
            tar_files_1 = [f for f in cache_files_1 if not f.endswith('.info')]
            
            # Load image second time
            success2, image_name2, error_msg2 = loader.load_image(tar_path)
            self.assertTrue(success2, f"Second load should succeed. Error: {error_msg2}")
            
            # Get cache state after second load
            cache_files_2 = set(os.listdir(cache_dir))
            tar_files_2 = [f for f in cache_files_2 if not f.endswith('.info')]
            
            # Should have same number of tar files (no duplicates)
            self.assertEqual(len(tar_files_1), len(tar_files_2),
                           "Should not create duplicate tar files")
            
            # Image names should match
            self.assertEqual(image_name1, image_name2,
                           "Image names should match on repeated loads")
            
            # Should still have only one tar file
            self.assertEqual(len(tar_files_2), 1,
                           "Should have exactly one cached tar file")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
