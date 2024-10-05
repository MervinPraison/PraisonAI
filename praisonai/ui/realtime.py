import os
import asyncio
from openai import AsyncOpenAI
import chainlit as cl
from uuid import uuid4
from chainlit.logger import logger
from realtimeclient import RealtimeClient
from realtimeclient.tools import tools
import json
from dotenv import load_dotenv
from chainlit.input_widget import TextInput
import logging
from PIL import Image
import io
import base64

load_dotenv()

# Set up logging
logger = logging.getLogger(__name__)
log_level = os.getenv("LOGLEVEL", "DEBUG").upper()
logger.setLevel(log_level)

client = AsyncOpenAI()

async def setup_openai_realtime():
    """Instantiate and configure the OpenAI Realtime Client"""
    openai_realtime = RealtimeClient(api_key=os.getenv("OPENAI_API_KEY"))
    cl.user_session.set("track_id", str(uuid4()))
    
    async def handle_conversation_updated(event):
        item = event.get("item")
        delta = event.get("delta")
        """Currently used to stream audio back to the client."""
        if delta:
            # Debug logging
            # debug_delta = {k: f"<{type(v).__name__} of length {len(v)}>" if isinstance(v, (bytes, bytearray)) else v for k, v in delta.items()}
            # logger.debug(f"Delta received: {json.dumps(debug_delta, indent=2)}")
            
            # Only one of the following will be populated for any given event
            if 'audio' in delta:
                audio = delta['audio']  # Int16Array, audio added
                await cl.context.emitter.send_audio_chunk(cl.OutputAudioChunk(mimeType="pcm16", data=audio, track=cl.user_session.get("track_id")))
            if 'transcript' in delta:
                transcript = delta['transcript']  # string, transcript added
                # logger.debug(f"Transcript delta: {transcript}")
            if 'text' in delta:
                text = delta['text']  # string, text added
                # logger.debug(f"Text delta: {text}")
            if 'arguments' in delta:
                arguments = delta['arguments']  # string, function arguments added
                # logger.debug(f"Function arguments delta: {arguments}")
    
    async def handle_item_completed(event):
        """Used to populate the chat context with transcription once an item is completed."""
        try:
            item = event.get("item")
            # logger.debug(f"Item completed: {json.dumps(item, indent=2, default=str)}")
            openai_realtime = cl.user_session.get("openai_realtime")
            await openai_realtime._send_chainlit_message(item)
        except Exception as e:
            error_message = f"Error in handle_item_completed: {str(e)}"
            logger.error(error_message)
            
            debug_item = json.dumps(item, indent=2, default=str)
            logger.error(f"Item causing error: {debug_item}")
    
    async def handle_conversation_interrupt(event):
        """Used to cancel the client previous audio playback."""
        cl.user_session.set("track_id", str(uuid4()))
        await cl.context.emitter.send_audio_interrupt()
        
    async def handle_error(event):
        logger.error(event)
        await cl.Message(content=f"Error: {event}", author="System").send()
    
    openai_realtime.on('conversation.updated', handle_conversation_updated)
    openai_realtime.on('conversation.item.completed', handle_item_completed)
    openai_realtime.on('conversation.interrupted', handle_conversation_interrupt)
    openai_realtime.on('error', handle_error)

    cl.user_session.set("openai_realtime", openai_realtime)
    coros = [openai_realtime.add_tool(tool_def, tool_handler) for tool_def, tool_handler in tools]
    await asyncio.gather(*coros)

@cl.on_chat_start
async def start():
    model_name = os.getenv("MODEL_NAME", "gpt-4o-mini")
    cl.user_session.set("model_name", model_name)
    settings = cl.ChatSettings(
        [
            TextInput(
                id="model_name",
                label="Enter the Model Name",
                placeholder="e.g., gpt-4o-mini",
                initial=model_name
            )
        ]
    )
    cl.user_session.set("settings", settings)
    await settings.send()
    
    await cl.Message(
        content="Welcome to the Chainlit x OpenAI realtime example. Press `P` to talk!"
    ).send()
    await setup_openai_realtime()

@cl.on_settings_update
async def setup_agent(settings):
    logger.debug(settings)
    cl.user_session.set("settings", settings)
    model_name = settings["model_name"]
    cl.user_session.set("model_name", model_name)

@cl.on_message
async def on_message(message: cl.Message):
    openai_realtime: RealtimeClient = cl.user_session.get("openai_realtime")
    if openai_realtime and openai_realtime.is_connected():
        # Check if an image was uploaded with this message
        image = None
        if message.elements and isinstance(message.elements[0], cl.Image):
            image_element = message.elements[0]
            try:
                # Open the image and keep it in memory
                image = Image.open(image_element.path)
                image.load()  # This ensures the file is fully loaded into memory
                cl.user_session.set("image", image)
            except Exception as e:
                logger.error(f"Error processing image: {str(e)}")
                await cl.Message(content="There was an error processing the uploaded image. Please try again.").send()
                return

        # Prepare user message
        user_message = [{ "type": 'input_text', "text": message.content }]

        # If an image is uploaded, include it in the message
        if image:
            buffered = io.BytesIO()
            image.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode()
            user_message.append({ "type": 'image', "image_url": f"data:image/png;base64,{img_str}" })

        await openai_realtime.send_user_message_content(user_message)
    else:
        await cl.Message(content="Please activate voice mode before sending messages!").send()

@cl.on_audio_start
async def on_audio_start():
    try:
        openai_realtime: RealtimeClient = cl.user_session.get("openai_realtime")
        # TODO: might want to recreate items to restore context
        # openai_realtime.create_conversation_item(item)
        await openai_realtime.connect()
        logger.info("Connected to OpenAI realtime")
        return True
    except Exception as e:
        await cl.ErrorMessage(content=f"Failed to connect to OpenAI realtime: {e}").send()
        return False

@cl.on_audio_chunk
async def on_audio_chunk(chunk: cl.InputAudioChunk):
    openai_realtime: RealtimeClient = cl.user_session.get("openai_realtime")            
    if openai_realtime.is_connected():
        await openai_realtime.append_input_audio(chunk.data)
    else:
        logger.info("RealtimeClient is not connected")

@cl.on_audio_end
@cl.on_chat_end
@cl.on_stop
async def on_end():
    openai_realtime: RealtimeClient = cl.user_session.get("openai_realtime")
    if openai_realtime and openai_realtime.is_connected():
        await openai_realtime.disconnect()