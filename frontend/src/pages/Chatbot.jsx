import React, { useState, useRef, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { healthApi } from '../api/axios';
import Navbar from '../components/Navbar';
import '../Chatbot.css'; // We'll create this

export default function Chatbot() {
  const [messages, setMessages] = useState([
    { text: "Hello! I am your MediLink AI assistant. How can I help you today?", sender: 'bot', isFallback: false }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);
  const [searchParams] = useSearchParams();
  const appointmentId = searchParams.get('appointment_id');

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  const handleSend = async (e) => {
    if (e) e.preventDefault();
    if (!input.trim()) return;

    const userMsg = { text: input, sender: 'user' };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const { data } = await healthApi.post('/chat', { 
        message: userMsg.text,
        appointment_id: appointmentId || undefined
      });
      setMessages((prev) => [
        ...prev,
        { text: data.reply, sender: 'bot', isFallback: data.is_fallback }
      ]);
    } catch (err) {
      console.error(err);
      setMessages((prev) => [
        ...prev,
        { 
          text: "I'm having trouble connecting right now. Please try again later.", 
          sender: 'bot', 
          isFallback: true 
        }
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app-layout">
      <Navbar />
      <main className="main-content">
        <div className="chatbot-container">
          <div className="chatbot-header">
            <h2>MediLink AI Assistant</h2>
            <p>Describe your symptoms or ask a health question</p>
          </div>
          
          <div className="chatbot-messages">
            {messages.map((msg, index) => (
              <div key={index} className={`message-wrapper ${msg.sender}`}>
                <div className="message-bubble">
                  {msg.text}
              </div>
            ))}
            {loading && (
              <div className="message-wrapper bot">
                <div className="message-bubble typing-indicator">
                  <span></span><span></span><span></span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <form className="chatbot-input-form" onSubmit={handleSend}>
            <input
              type="text"
              placeholder="Type your message..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={loading}
            />
            <button type="submit" disabled={!input.trim() || loading} className="btn btn-primary">
              Send
            </button>
          </form>
        </div>
      </main>
    </div>
  );
}
