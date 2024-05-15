import React, { useState } from 'react';
import {
  Container,
  FormControl,
  FormLabel,
  Input,
  Button,
  VStack,
} from '@chakra-ui/react';

// Mocking wpApiSettings for development purposes. This should be replaced with the actual object provided by WordPress in production.
const wpApiSettings = { nonce: 'dev-nonce' }; // This line is added to mock the wpApiSettings object

const SettingsForm = () => {
  const [patreonClientId, setPatreonClientId] = useState('');
  const [patreonClientSecret, setPatreonClientSecret] = useState('');
  const [youtubeApiKey, setYoutubeApiKey] = useState('');
  const [file, setFile] = useState(null);

  const handleSubmit = (event) => {
    event.preventDefault();
    // Handle the submission logic here
    // This will involve saving the API credentials to the WordPress database
    // For now, we'll log the credentials to the console
    console.log({
      patreonClientId,
      patreonClientSecret,
      youtubeApiKey,
    });
    // TODO: Implement API call to save these settings in WordPress
  };

  const handleFileChange = (event) => {
    setFile(event.target.files[0]);
  };

  const handleFileUpload = async (event) => {
    event.preventDefault();
    if (file) {
      const formData = new FormData();
      formData.append('file', file);

      try {
        const response = await fetch('/wp-json/patreon-youtube/v1/upload_media', {
          method: 'POST',
          headers: {
            'X-WP-Nonce': wpApiSettings.nonce,
          },
          body: formData,
        });

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const result = await response.json();
        console.log('File uploaded successfully:', result);
        // TODO: Handle the successful upload (e.g., display a success message, clear the form, etc.)
      } catch (error) {
        console.error('File upload error:', error);
        // TODO: Handle the upload error (e.g., display an error message to the user)
      }
    } else {
      console.error('No file selected');
      // TODO: Inform the user that no file was selected
    }
  };

  return (
    <Container>
      <form onSubmit={handleSubmit}>
        <VStack spacing={4}>
          <FormControl id="patreon-client-id">
            <FormLabel>Patreon Client ID</FormLabel>
            <Input
              type="text"
              value={patreonClientId}
              onChange={(e) => setPatreonClientId(e.target.value)}
            />
          </FormControl>
          <FormControl id="patreon-client-secret">
            <FormLabel>Patreon Client Secret</FormLabel>
            <Input
              type="text"
              value={patreonClientSecret}
              onChange={(e) => setPatreonClientSecret(e.target.value)}
            />
          </FormControl>
          <FormControl id="youtube-api-key">
            <FormLabel>YouTube API Key</FormLabel>
            <Input
              type="text"
              value={youtubeApiKey}
              onChange={(e) => setYoutubeApiKey(e.target.value)}
            />
          </FormControl>
          <FormControl id="file-upload">
            <FormLabel>Upload Media</FormLabel>
            <Input
              type="file"
              onChange={handleFileChange}
            />
            <Button onClick={handleFileUpload} colorScheme="blue">Upload</Button>
          </FormControl>
          <Button type="submit" colorScheme="blue">Save Settings</Button>
        </VStack>
      </form>
    </Container>
  );
};

export default SettingsForm;
