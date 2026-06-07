import React, { useState } from 'react';
import { Box, Typography, TextField, Button, Paper, List, ListItem, ListItemText, CircularProgress } from '@mui/material';
import SendIcon from '@mui/icons-material/Send';

export default function Chatbot() {
  const [messages, setMessages] = useState([
    { text: "Hello! I am your MediLink AI assistant. How can I help you today?", sender: 'bot' }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSend = () => {
    if (!input.trim()) return;

    const userMsg = { text: input, sender: 'user' };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    // Mock AI response
    setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        { text: "I'm still learning, but I can help you find doctors and manage your appointments soon!", sender: 'bot' }
      ]);
      setLoading(false);
    }, 1500);
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter') {
      handleSend();
    }
  };

  return (
    <Box sx={{ maxWidth: 800, mx: 'auto', mt: 4, p: 2 }}>
      <Typography variant="h4" gutterBottom align="center" sx={{ fontWeight: 'bold', color: 'primary.main' }}>
        MediLink AI Assistant
      </Typography>
      <Paper elevation={3} sx={{ height: '60vh', display: 'flex', flexDirection: 'column', p: 2, borderRadius: 3 }}>
        <Box sx={{ flexGrow: 1, overflowY: 'auto', mb: 2 }}>
          <List>
            {messages.map((msg, index) => (
              <ListItem key={index} sx={{ display: 'flex', justifyContent: msg.sender === 'user' ? 'flex-end' : 'flex-start' }}>
                <Paper 
                  elevation={1} 
                  sx={{ 
                    p: 2, 
                    maxWidth: '70%',
                    backgroundColor: msg.sender === 'user' ? 'primary.main' : 'grey.100',
                    color: msg.sender === 'user' ? 'white' : 'text.primary',
                    borderRadius: 2
                  }}
                >
                  <ListItemText primary={msg.text} />
                </Paper>
              </ListItem>
            ))}
            {loading && (
              <ListItem sx={{ display: 'flex', justifyContent: 'flex-start' }}>
                <CircularProgress size={24} />
              </ListItem>
            )}
          </List>
        </Box>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <TextField
            fullWidth
            variant="outlined"
            placeholder="Type your message..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
          />
          <Button 
            variant="contained" 
            color="primary" 
            onClick={handleSend}
            disabled={!input.trim() || loading}
            sx={{ px: 4 }}
          >
            <SendIcon />
          </Button>
        </Box>
      </Paper>
    </Box>
  );
}
