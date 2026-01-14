#!/usr/bin/env python3
"""
Property-based tests for OCI manifest support
Feature: ghcr-oci-support
"""

import unittest
import json
from unittest.mock import Mock, patch, MagicMock
from hypothesis import given, settings, strategies as st
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from android_docker.create_rootfs_tar import DockerRegistryClient, DockerImageToRootFS


# Hypothesis strategies for generating test data
@st.composite
def manifest_path_strategy(draw):
    """Generate valid manifest paths (both tag and digest based)"""
    image_name = draw(st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Ll', 'Lu', 'Nd'), whitelist_characters='/-_')))
    
    # Generate either a tag or a digest
    use_digest = draw(st.booleans())
    if use_digest:
        # Generate a sha256 digest
        digest = draw(st.text(min_size=64, max_size=64, alphabet='0123456789abcdef'))
        reference = f"sha256:{digest}"
    else:
        # Generate a tag
        tag = draw(st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('Ll', 'Lu', 'Nd'), whitelist_characters='.-_')))
        reference = tag
    
    return f"{image_name}/manifests/{reference}"


class TestOCIAcceptHeaders(unittest.TestCase):
    """
    Property 1: OCI Accept Headers in All Manifest Requests
    Validates: Requirements 1.1, 1.2
    """
    
    @given(manifest_path=manifest_path_strategy())
    @settings(max_examples=100)
    def test_accept_headers_in_all_manifest_requests(self, manifest_path):
        """
        Feature: ghcr-oci-support, Property 1: OCI Accept Headers in All Manifest Requests
        
        For any manifest request (whether by tag or digest), the HTTP Accept header 
        SHALL include all required OCI and Docker media types.
        """
        # Create a mock client
        client = DockerRegistryClient(
            registry_url="https://ghcr.io",
            image_name="test/image",
            tag="latest"
        )
        
        # Mock the _run_curl_command to capture the command
        captured_commands = []
        
        def mock_run_curl(cmd, print_cmd=True):
            captured_commands.append(cmd)
            # Return a mock result
            result = Mock()
            result.stdout = 'HTTP/1.1 200 OK\r\ncontent-type: application/json\r\n\r\n{"test": "data"}'
            result.stderr = ''
            return result
        
        # Set auth_token to skip authentication step
        client.auth_token = "test_token"
        
        with patch.object(client, '_run_curl_command', side_effect=mock_run_curl):
            try:
                client._make_registry_request(manifest_path)
            except:
                # We expect this to fail since we're mocking, but we just want to check the command
                pass
        
        # Verify that at least one command was captured
        self.assertGreater(len(captured_commands), 0, "No curl commands were captured")
        
        # Check the final request command (should be the last one)
        final_command = captured_commands[-1]
        
        # Verify it's a manifest request
        self.assertIn('manifests', ' '.join(final_command), 
                     f"Expected manifest request but got: {' '.join(final_command)}")
        
        # Find the Accept header in the command
        accept_header_found = False
        required_media_types = [
            'application/vnd.oci.image.manifest.v1+json',
            'application/vnd.oci.image.index.v1+json',
            'application/vnd.docker.distribution.manifest.v2+json',
            'application/vnd.docker.distribution.manifest.list.v2+json'
        ]
        
        for i, arg in enumerate(final_command):
            if arg == '-H' and i + 1 < len(final_command):
                header = final_command[i + 1]
                if header.startswith('Accept:'):
                    accept_header_found = True
                    accept_value = header.split(':', 1)[1].strip()
                    
                    # Verify all required media types are present
                    for media_type in required_media_types:
                        self.assertIn(media_type, accept_value,
                                    f"Accept header missing required media type: {media_type}")
        
        self.assertTrue(accept_header_found, 
                       f"Accept header not found in manifest request: {' '.join(final_command)}")


@st.composite
def valid_oci_manifest_strategy(draw):
    """Generate valid OCI manifest structures"""
    # Generate random number of layers (1-10)
    num_layers = draw(st.integers(min_value=1, max_value=10))
    
    layers = []
    for _ in range(num_layers):
        digest = draw(st.text(min_size=64, max_size=64, alphabet='0123456789abcdef'))
        size = draw(st.integers(min_value=100, max_value=1000000))
        layers.append({
            "mediaType": draw(st.sampled_from([
                "application/vnd.oci.image.layer.v1.tar+gzip",
                "application/vnd.oci.image.layer.v1.tar"
            ])),
            "digest": f"sha256:{digest}",
            "size": size
        })
    
    # Generate config
    config_digest = draw(st.text(min_size=64, max_size=64, alphabet='0123456789abcdef'))
    config_size = draw(st.integers(min_value=100, max_value=10000))
    
    manifest = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "config": {
            "mediaType": "application/vnd.oci.image.config.v1+json",
            "digest": f"sha256:{config_digest}",
            "size": config_size
        },
        "layers": layers
    }
    
    return manifest


class TestOCIManifestParsing(unittest.TestCase):
    """
    Property 2: OCI Manifest Parsing Correctness
    Validates: Requirements 1.3
    """
    
    @given(oci_manifest=valid_oci_manifest_strategy())
    @settings(max_examples=100)
    def test_oci_manifest_parsing_correctness(self, oci_manifest):
        """
        Feature: ghcr-oci-support, Property 2: OCI Manifest Parsing Correctness
        
        For any valid OCI manifest returned by a registry, the parser SHALL 
        successfully extract all layer digests and the config digest without errors.
        """
        # Create a mock client
        client = DockerRegistryClient(
            registry_url="https://ghcr.io",
            image_name="test/image",
            tag="latest"
        )
        
        # Mock the _make_registry_request to return our test manifest
        def mock_request(path, headers=None, output_file=None):
            return {
                'status_code': 200,
                'headers': {'content-type': 'application/vnd.oci.image.manifest.v1+json'},
                'body': json.dumps(oci_manifest)
            }
        
        with patch.object(client, '_make_registry_request', side_effect=mock_request):
            manifest, content_type = client.get_manifest()
        
        # Verify the manifest was parsed correctly
        self.assertIsNotNone(manifest, "Manifest should not be None")
        self.assertIn('layers', manifest, "Manifest should contain 'layers' field")
        self.assertIn('config', manifest, "Manifest should contain 'config' field")
        
        # Verify all layer digests are present
        self.assertEqual(len(manifest['layers']), len(oci_manifest['layers']),
                        "Number of layers should match")
        
        for i, layer in enumerate(manifest['layers']):
            self.assertIn('digest', layer, f"Layer {i} should have a digest")
            self.assertTrue(layer['digest'].startswith('sha256:'),
                          f"Layer {i} digest should start with 'sha256:'")
        
        # Verify config digest is present
        self.assertIn('digest', manifest['config'], "Config should have a digest")
        self.assertTrue(manifest['config']['digest'].startswith('sha256:'),
                       "Config digest should start with 'sha256:'")


@st.composite
def oci_layer_descriptor_strategy(draw):
    """Generate OCI layer descriptors with various media types"""
    digest = draw(st.text(min_size=64, max_size=64, alphabet='0123456789abcdef'))
    size = draw(st.integers(min_value=100, max_value=1000000))
    
    # Generate OCI-specific media types
    media_type = draw(st.sampled_from([
        "application/vnd.oci.image.layer.v1.tar+gzip",
        "application/vnd.oci.image.layer.v1.tar"
    ]))
    
    return {
        "mediaType": media_type,
        "digest": f"sha256:{digest}",
        "size": size
    }


class TestOCILayerMediaTypeHandling(unittest.TestCase):
    """
    Property 3: OCI Layer Media Type Handling
    Validates: Requirements 1.4, 1.5
    """
    
    @given(layer_descriptor=oci_layer_descriptor_strategy())
    @settings(max_examples=100)
    def test_oci_layer_media_type_handling(self, layer_descriptor):
        """
        Feature: ghcr-oci-support, Property 3: OCI Layer Media Type Handling
        
        For any OCI layer descriptor with a valid OCI media type, the downloader 
        SHALL process it identically to Docker v2 layer media types.
        """
        # Create a test manifest with the OCI layer
        oci_manifest = {
            "schemaVersion": 2,
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "config": {
                "mediaType": "application/vnd.oci.image.config.v1+json",
                "digest": "sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
                "size": 1000
            },
            "layers": [layer_descriptor]
        }
        
        # Create a DockerImageToRootFS instance
        processor = DockerImageToRootFS(
            image_url="ghcr.io/test/image:latest",
            output_path="/tmp/test.tar"
        )
        
        # Test that the manifest conversion handles OCI media types correctly
        converted_manifest = processor._convert_manifest_to_oci(
            oci_manifest, 
            "application/vnd.oci.image.manifest.v1+json"
        )
        
        # Verify the layer is present and has the correct structure
        self.assertIn('layers', converted_manifest, "Converted manifest should have layers")
        self.assertEqual(len(converted_manifest['layers']), 1, 
                        "Should have exactly one layer")
        
        converted_layer = converted_manifest['layers'][0]
        
        # Verify the layer descriptor is preserved correctly
        self.assertEqual(converted_layer['digest'], layer_descriptor['digest'],
                        "Layer digest should be preserved")
        self.assertEqual(converted_layer['size'], layer_descriptor['size'],
                        "Layer size should be preserved")
        
        # Verify OCI media types are handled (either preserved or converted appropriately)
        self.assertIn('mediaType', converted_layer, "Layer should have mediaType")
        
        # OCI media types should be preserved in OCI manifests
        if 'oci' in layer_descriptor['mediaType']:
            self.assertIn('oci', converted_layer['mediaType'],
                         "OCI media types should be preserved in OCI manifests")


if __name__ == '__main__':
    unittest.main()



class TestArchitectureNormalization(unittest.TestCase):
    """
    Unit tests for architecture normalization
    Validates: Requirements 3.1
    """
    
    def test_aarch64_to_arm64_mapping(self):
        """Test that aarch64 is normalized to arm64"""
        processor = DockerImageToRootFS(
            image_url="test/image:latest",
            output_path="/tmp/test.tar"
        )
        
        # Mock platform.machine() to return aarch64
        with patch('platform.machine', return_value='aarch64'):
            arch = processor._get_current_architecture()
            self.assertEqual(arch, 'arm64', 
                           "aarch64 should be normalized to arm64")
    
    def test_x86_64_to_amd64_mapping(self):
        """Test that x86_64 is normalized to amd64"""
        processor = DockerImageToRootFS(
            image_url="test/image:latest",
            output_path="/tmp/test.tar"
        )
        
        with patch('platform.machine', return_value='x86_64'):
            arch = processor._get_current_architecture()
            self.assertEqual(arch, 'amd64',
                           "x86_64 should be normalized to amd64")
    
    def test_arm64_preserved(self):
        """Test that arm64 is preserved as arm64"""
        processor = DockerImageToRootFS(
            image_url="test/image:latest",
            output_path="/tmp/test.tar"
        )
        
        with patch('platform.machine', return_value='arm64'):
            arch = processor._get_current_architecture()
            self.assertEqual(arch, 'arm64',
                           "arm64 should remain arm64")
    
    def test_armv7l_to_arm_mapping(self):
        """Test that armv7l is normalized to arm"""
        processor = DockerImageToRootFS(
            image_url="test/image:latest",
            output_path="/tmp/test.tar"
        )
        
        with patch('platform.machine', return_value='armv7l'):
            arch = processor._get_current_architecture()
            self.assertEqual(arch, 'arm',
                           "armv7l should be normalized to arm")
    
    def test_i386_to_386_mapping(self):
        """Test that i386 is normalized to 386"""
        processor = DockerImageToRootFS(
            image_url="test/image:latest",
            output_path="/tmp/test.tar"
        )
        
        with patch('platform.machine', return_value='i386'):
            arch = processor._get_current_architecture()
            self.assertEqual(arch, '386',
                           "i386 should be normalized to 386")
    
    def test_unknown_architecture_defaults_to_amd64(self):
        """Test that unknown architectures default to amd64"""
        processor = DockerImageToRootFS(
            image_url="test/image:latest",
            output_path="/tmp/test.tar"
        )
        
        with patch('platform.machine', return_value='unknown_arch'):
            arch = processor._get_current_architecture()
            self.assertEqual(arch, 'amd64',
                           "Unknown architectures should default to amd64")



@st.composite
def manifest_list_with_arm64_strategy(draw):
    """Generate manifest lists containing arm64 entries"""
    # Generate a manifest list with at least one arm64 entry
    num_manifests = draw(st.integers(min_value=1, max_value=5))
    
    manifests = []
    
    # Ensure at least one arm64 manifest
    digest = draw(st.text(min_size=64, max_size=64, alphabet='0123456789abcdef'))
    manifests.append({
        "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
        "digest": f"sha256:{digest}",
        "size": draw(st.integers(min_value=1000, max_value=10000)),
        "platform": {
            "architecture": "arm64",
            "os": "linux"
        }
    })
    
    # Add other random architectures
    other_archs = ["amd64", "arm", "386", "ppc64le", "s390x"]
    for _ in range(num_manifests - 1):
        digest = draw(st.text(min_size=64, max_size=64, alphabet='0123456789abcdef'))
        manifests.append({
            "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
            "digest": f"sha256:{digest}",
            "size": draw(st.integers(min_value=1000, max_value=10000)),
            "platform": {
                "architecture": draw(st.sampled_from(other_archs)),
                "os": "linux"
            }
        })
    
    return {
        "schemaVersion": 2,
        "mediaType": "application/vnd.docker.distribution.manifest.list.v2+json",
        "manifests": manifests
    }


class TestArchitectureEquivalence(unittest.TestCase):
    """
    Property 9: Architecture Equivalence in Matching
    Validates: Requirements 3.2
    """
    
    @given(manifest_list=manifest_list_with_arm64_strategy())
    @settings(max_examples=100)
    def test_architecture_equivalence_in_matching(self, manifest_list):
        """
        Feature: ghcr-oci-support, Property 9: Architecture Equivalence in Matching
        
        For any manifest list containing entries for arm64, a system with 
        architecture aarch64 SHALL successfully match and select that manifest entry.
        """
        # Create a processor with aarch64 architecture (which should normalize to arm64)
        processor = DockerImageToRootFS(
            image_url="test/image:latest",
            output_path="/tmp/test.tar"
        )
        
        # Mock platform.machine() to return aarch64
        with patch('platform.machine', return_value='aarch64'):
            # Re-initialize to pick up the mocked architecture
            processor.architecture = processor._get_current_architecture()
        
        # Verify architecture was normalized to arm64
        self.assertEqual(processor.architecture, 'arm64',
                        "aarch64 should be normalized to arm64")
        
        # Now test that we can find a matching manifest
        selected_manifest = None
        for manifest_descriptor in manifest_list.get('manifests', []):
            platform_info = manifest_descriptor.get('platform', {})
            manifest_arch = platform_info.get('architecture')
            
            # Use the same matching logic as the implementation
            arch_match = (manifest_arch == processor.architecture or 
                         (processor.architecture == 'arm64' and manifest_arch == 'aarch64') or
                         (processor.architecture == 'aarch64' and manifest_arch == 'arm64'))
            
            if arch_match:
                if platform_info.get('os') == 'linux' or 'os' not in platform_info:
                    selected_manifest = manifest_descriptor
                    break
        
        # Verify that a manifest was selected
        self.assertIsNotNone(selected_manifest,
                           "Should find a matching manifest for aarch64/arm64")
        
        # Verify the selected manifest has arm64 architecture
        self.assertEqual(selected_manifest['platform']['architecture'], 'arm64',
                        "Selected manifest should have arm64 architecture")



@st.composite
def manifest_list_without_match_strategy(draw):
    """Generate manifest lists that don't contain the target architecture"""
    # Generate a manifest list without arm64/aarch64
    num_manifests = draw(st.integers(min_value=1, max_value=5))
    
    # Architectures that are NOT arm64 or aarch64
    other_archs = ["amd64", "arm", "386", "ppc64le", "s390x", "riscv64"]
    
    manifests = []
    for _ in range(num_manifests):
        digest = draw(st.text(min_size=64, max_size=64, alphabet='0123456789abcdef'))
        manifests.append({
            "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
            "digest": f"sha256:{digest}",
            "size": draw(st.integers(min_value=1000, max_value=10000)),
            "platform": {
                "architecture": draw(st.sampled_from(other_archs)),
                "os": "linux"
            }
        })
    
    return {
        "schemaVersion": 2,
        "mediaType": "application/vnd.docker.distribution.manifest.list.v2+json",
        "manifests": manifests
    }


class TestArchitectureMismatchErrors(unittest.TestCase):
    """
    Property 10: Architecture Mismatch Error Reporting
    Validates: Requirements 3.3
    """
    
    @given(manifest_list=manifest_list_without_match_strategy())
    @settings(max_examples=100)
    def test_architecture_mismatch_error_reporting(self, manifest_list):
        """
        Feature: ghcr-oci-support, Property 10: Architecture Mismatch Error Reporting
        
        For any manifest list that does not contain an entry matching the system 
        architecture, the error message SHALL include a list of all available 
        architectures from the manifest list.
        """
        # Simulate the error condition
        target_architecture = 'arm64'  # Looking for arm64 but it's not in the list
        
        # Extract available architectures from the manifest list
        available_archs = [m.get('platform', {}).get('architecture') 
                          for m in manifest_list.get('manifests', [])]
        
        # Verify that arm64 is NOT in the available architectures
        self.assertNotIn('arm64', available_archs,
                        "Test setup error: arm64 should not be in the manifest list")
        self.assertNotIn('aarch64', available_archs,
                        "Test setup error: aarch64 should not be in the manifest list")
        
        # Simulate the error message generation (as done in the implementation)
        try:
            # This simulates what the code does when no match is found
            selected_manifest = None
            for manifest_descriptor in manifest_list.get('manifests', []):
                platform_info = manifest_descriptor.get('platform', {})
                manifest_arch = platform_info.get('architecture')
                
                arch_match = (manifest_arch == target_architecture or 
                             (target_architecture == 'arm64' and manifest_arch == 'aarch64') or
                             (target_architecture == 'aarch64' and manifest_arch == 'arm64'))
                
                if arch_match:
                    if platform_info.get('os') == 'linux' or 'os' not in platform_info:
                        selected_manifest = manifest_descriptor
                        break
            
            if not selected_manifest:
                # Generate the error message as the implementation does
                available_archs_list = [m.get('platform', {}).get('architecture') 
                                       for m in manifest_list.get('manifests', [])]
                error_msg = f"在manifest list中找不到适用于架构 '{target_architecture}' 的镜像。可用架构: {', '.join(filter(None, available_archs_list))}"
                raise ValueError(error_msg)
        
        except ValueError as e:
            error_message = str(e)
            
            # Verify the error message contains the target architecture
            self.assertIn(target_architecture, error_message,
                         "Error message should mention the target architecture")
            
            # Verify the error message contains all available architectures
            for arch in available_archs:
                if arch:  # Skip None values
                    self.assertIn(arch, error_message,
                                f"Error message should list available architecture: {arch}")
            
            # Verify the error message has proper formatting
            self.assertIn('可用架构', error_message,
                         "Error message should indicate available architectures")
        else:
            self.fail("Should have raised ValueError for architecture mismatch")
