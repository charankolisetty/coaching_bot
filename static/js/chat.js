$(document).ready(function() {
    const chatMessages = $('#chat-messages');
    const chatForm = $('#chat-form');
    const promptInput = $('#prompt');

    // Add welcome message
    addMessage("Hi! I'm your coach bot. How can I help you today?", 'bot');

    chatForm.on('submit', function(e) {
        e.preventDefault();
        
        const prompt = promptInput.val().trim();
        if (!prompt) return;

        // Disable form and show user message
        chatForm.addClass('disabled');
        addMessage(prompt, 'user');
        promptInput.val('');

        // Show typing indicator
        showTypingIndicator();

        // Send request to server
        $.ajax({
            url: '/chat',
            method: 'POST',
            data: { prompt: prompt },
            success: function(response) {
                // Remove typing indicator and add bot response
                removeTypingIndicator();
                addMessage(response.response, 'bot');
            },
            error: function(xhr, status, error) {
                // Remove typing indicator and show error
                removeTypingIndicator();
                const errorMessage = xhr.responseJSON?.error || 'An error occurred. Please try again.';
                addMessage(`Error: ${errorMessage}`, 'bot error');
            },
            complete: function() {
                // Re-enable form
                chatForm.removeClass('disabled');
                // Scroll to bottom
                scrollToBottom();
            }
        });
    });

    function addMessage(text, type) {
        const messageDiv = $('<div>')
            .addClass('message')
            .addClass(`${type}-message`)
            .text(text);
        chatMessages.append(messageDiv);
        scrollToBottom();
    }

    function showTypingIndicator() {
        const indicator = $('<div class="typing-indicator"><span></span><span></span><span></span></div>');
        chatMessages.append(indicator);
        scrollToBottom();
    }

    function removeTypingIndicator() {
        $('.typing-indicator').remove();
    }

    function scrollToBottom() {
        chatMessages.scrollTop(chatMessages[0].scrollHeight);
    }

    // Handle enter key
    promptInput.on('keypress', function(e) {
        if (e.which == 13 && !e.shiftKey) {
            chatForm.submit();
            return false;
        }
    });
});