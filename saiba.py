## here we will create an app to have a discord bot for our server
## the app will use google gemini api and discord.py
import asyncio
import datetime
import discord
from bot_logic import *
from discord.ext import commands
from discord.ext import tasks
from cachetools import LRUCache
import os 
from dotenv import load_dotenv


load_dotenv()


## here we will put the key of the discord bot and gemini app
## here to be able to provision the code online we need to remove the hardcoded token
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

## here we define the fact checker channel id variable
FACT_CHECKER_CHANNEL = 1413456389203820584

## here we define the different message history limits

THREAD_NEWEST_LIMIT = 50
THREAD_OLDEST_LIMIT = 100

## here we define the limit for discussion
## same for oldest and newest
DISCUSSION_LIMIT = 200



## here we will start by getting the message from the bot
## create the intents, they enable the bot to have some permissions or not using defaults enables most except message content
intents = discord.Intents.default()
## eneable message content
intents.message_content = True 
intents.guilds = True
intents.messages = True
#intents.members = True

## create a discord client listen to discord object with the different intents
## we create it with commands bot to be able to use cogs
saiba_ears = commands.Bot(command_prefix='!', intents=intents)


## cog to reply in threads
class ThreadDiscussionCog(commands.Cog):
    def __init__(self, bot):
        ## to init the bot 
        self.bot = bot
        self.active_thread = LRUCache(maxsize=200)
        self.channel_topic = ""

    @commands.Cog.listener()
    ## we first listen for the thread creation
    async def on_thread_create(self, thread):
        ## after the first message will be sent to the thread the thread will be created
        print(f"Thread created with the id: {thread.id}")
        ## get the thread channel topic
        self.channel_topic = thread.parent.topic
        ## we check if the thread is not in the dictionnary of active thread
        ## if not we create the thread key
        if thread.id not in self.active_thread:
            ## the key is associated with a dictionnary with two list newest and oldest
            self.active_thread[thread.id] = {
                "newest": [],
                "oldest": []
            }
            ## we get the starter message of the thread metadata to store
            message_metadata = {
            "author_id" : thread.starter_message.author.id,
            "author_name" : thread.starter_message.author.global_name,
            "content" : thread.starter_message.content,
            "timestamp": thread.starter_message.created_at
            }
            ## because it is the first message it is appended at the begining of the list
            self.active_thread[thread.id]["newest"].insert(0, message_metadata)
        
    @commands.Cog.listener()

    async def on_message(self, message):
        ## here once a message is listened to we get its metadata
        message_metadata = {
            "author_id" : message.author.id,
            "author_name" : message.author.global_name,
            "content" : message.content,
            "timestamp": message.created_at
            }       
        ## here we check if the message channel id is in the dictionnary if yes it means it is in an existing thread
        if message.channel.id in self.active_thread:
            ## because the first message is empty due to thread starting we forget the first message
            if message.content == "":
                print("The message was empty due to thread's creation, do not consider\n")
            else:
                ## here we get the message and continue the logic for the rest of the class
                if message.author == self.bot.user:
                        return
                
                print("adding the thread's latest message metadata...\n")
                ## add the metadata to the list
                self.active_thread[message.channel.id]["newest"].insert(0, message_metadata)

                ## here we check if the length of the list if superior to the required length
                if len(self.active_thread[message.channel.id]["newest"]) > THREAD_NEWEST_LIMIT:
                    ## if true it is sent to the list of oldest conv
                    data_summarize = self.active_thread[message.channel.id]["newest"].pop()
                    self.active_thread[message.channel.id]["oldest"].insert(0, data_summarize)
                ## here we check if the list of old message is above the limit
                if len(self.active_thread[message.channel.id]["oldest"]) > THREAD_OLDEST_LIMIT:
                    ## if yes the message if discarded
                    self.active_thread[message.channel.id]["oldest"].pop()

                ## here we check if the bot was mentionned
                bot_mentionned = self.bot.user in message.mentions

                new_conv = ""
                old_conv = ""

                if bot_mentionned == True:
                    ## if the bot is mentionned
                    print("Getting the thread to send message...\n")

                    ## we first get the summary of message 
                    for message_sent in reversed(self.active_thread[message.channel.id]["newest"]):
                        new_conv += f"Sent from {message_sent["author_name"]} at {message_sent["timestamp"]}: {message_sent["content"]}\n"
                    ## we do the same for old conversation
                    for message_sent in reversed(self.active_thread[message.channel.id]["oldest"]):
                        old_conv += f"Sent from {message_sent["author_name"]} at {message_sent["timestamp"]}: {message_sent["content"]}\n"

                    ## we get a summary of the old conversation
                    summary_conv = gemini_conv_summarizer(conversation=old_conv)

                    ## here get the topic expert response

                    topic_response = gemini_topic_expert(conversation=new_conv, summary=summary_conv, topic=self.channel_topic)
                    
                    ## we respond to the thread 
                    print("sending reponse...")
                    bot_response = await message.channel.send(topic_response)
                    print("response sent!")
                    ## getting the bot metadata to send to the log
                    message_data = {
                            "author_id" : bot_response.author.id,
                            "author_name" : bot_response.author.name,
                            "content" : bot_response.content,
                            "timestamp": bot_response.created_at
                        }
                    print("adding bot's message to the log..\n")
                    ## add the bot response to the thread
                    self.active_thread[message.channel.id]["newest"].insert(0, message_data)
                    print("bot message added!\n")
                    


## here we will use the same logic for the cog thread but in a general discussion


class DiscussionCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_discussion = LRUCache(maxsize=12)

    ## here we listen to the action 
    @commands.Cog.listener()
    ## here we use the on_message function to listen to the message
    async def on_message(self, message):
        ## here we get the topic of the channel
        channel_topic = str(message.channel.topic)
        ## we listen to the author if the author is the bot we do nothing
        if message.author == self.bot.user:
            return
        
        ## get the channel id
        channel_id = message.channel.id
        ## here we make it aware of the fact checker

        if channel_id == FACT_CHECKER_CHANNEL:
            return
    
        if not isinstance(message.channel, discord.TextChannel):
            return

        ## we create the key in the dictionnary for the active threads
        if channel_id not in self.active_discussion:
            self.active_discussion[channel_id] = {
                "newest" : [],
                "oldest" : []
            }

            print(f"New Conv in channel! The id is: {channel_id}\n")


        ## here we create the message data to add to the thread
        message_data = {
            "author_id" : message.author.id,
            "author_name" : message.author.global_name,
            "content" : message.content,
            "timestamp": message.created_at
        }

        ## we will track the last 200 so that the bot know what the people are saying 
        ## here we add the latest message to the front of the list
        print("adding the channel's latest message metadata...\n")
        self.active_discussion[channel_id]["newest"].insert(0, message_data)

        ## if the list gets to 200 we pop the oldest to put it in the old message
        if len(self.active_discussion[channel_id]["newest"]) > DISCUSSION_LIMIT:

            data_to_summarize = self.active_discussion[channel_id]["newest"].pop()

            self.active_discussion[channel_id]["oldest"].insert(0, data_to_summarize)
        ## we add the old message to the front of the list of old 
        

        ## if the message get to 100 we just pop the message because too old
        if len(self.active_discussion[channel_id]["oldest"]) > DISCUSSION_LIMIT:
            print("the old message log has grown to large discarding the oldest...\n")
            self.active_discussion[channel_id]["oldest"].pop()


        ## here now we will handle the mentions 
        bot_mentionned = self.bot.user in message.mentions

        ## now if the bot was mentionned do something
        old_conv_thread = ""
        new_conv_thread = ""
        if bot_mentionned == True:
            print("Getting channel to send message...\n")
            ## here we will get the summary of the conversation
            ## we reverse the list because the oldest message is at the end
            for message_sent in reversed(self.active_discussion[channel_id]["oldest"]):
                ## we format the response
                old_conv_thread += f"Sent from {message_sent["author_name"]} at {message_sent["timestamp"]}: {message_sent["content"]}\n"
            ## here we get the newest conversation
            for message_sent in reversed(self.active_discussion[channel_id]["newest"]):
                ## we format the response
                new_conv_thread += f"Sent from {message_sent["author_name"]} at {message_sent["timestamp"]}: {message_sent["content"]}\n"

            
            ## here we generate a summary from gemini
            ## if the conversation is new therefore no summary
            summary_conv = gemini_conv_summarizer(conversation=old_conv_thread)


            ## here we get gemini to respond to the user based on the conversation and the summary of older conversation
            ## because it is in a topic channel then it also needs to be an expert for that topic


            topic_response = gemini_topic_expert(conversation=new_conv_thread, summary=summary_conv, topic=channel_topic)


            ## this where the gemini function will be used to send message
            bot_response = await message.channel.send(topic_response)
            ## here are the metadata of the gemini response


            ## we get the bot metadata
            message_data = {
            "author_id" : bot_response.author.id,
            "author_name" : bot_response.author.name,
            "content" : bot_response.content,
            "timestamp": bot_response.created_at
            }

            ## debug to confirm the message was sent 
            print("message sent!\n")
            print("adding bot's message to the log..\n")
            ## add the bot response to the thread
            self.active_discussion[channel_id]["newest"].insert(0, message_data)
            print("bot message added!\n")





## here we will create the fact checker cog for the bot
class FactCheckerCog(commands.Cog):
## here caching is not necessary because people won't be allowed to create threads only ask questions to fact check
## there for list that grows and then discard conversation are good enough
    def __init__(self, bot):
        ## we define the bot but also the conversation thread for context
        self.bot = bot
        ## here because we knpw the channel no need to have a dictionnary
        self.active_channel_newest = []
        self.active_channel_oldest = []

    @commands.Cog.listener()
    async def on_message(self, message):
        ## here we will work to create the fact checker bot
        if message.author == self.bot.user:
            return 
        ## check if the message was sent in the fact checking channel
        if message.channel.id != FACT_CHECKER_CHANNEL:
            return
        ## if in the fact check channel
        ## here we create the message data to add to the thread
        message_data = {
            "author_id" : message.author.id,
            "author_name" : message.author.global_name,
            "content" : message.content,
            "timestamp": message.created_at
            }
            ## we then insert the message in the list

        self.active_channel_newest.insert(0, message_data)
            ## here we check the length of the list
        if len(self.active_channel_newest) > 30:
                ## if too long we add the data to the old list
                data_old = self.active_channel_newest.pop()
                self.active_channel_oldest.insert(0, data_old)
            ## here we check for old conversation
        if len(self.active_channel_oldest) > 50:
                self.active_channel_oldest.pop()

            ## here we will check if the bot was mentionned
            ## we start by getting the message content
        raw_content = message.content
        clean_content = raw_content
            ## we check if the bot is in the mentions
        bot_mentionned = self.bot.user in message.mentions


        conv_old = ""
        conv_new = ""

        if bot_mentionned == True:
                ## if the bot is mentionned it get the thread of the conversation and a summary
                for message_sent in reversed(self.active_channel_newest):
                    conv_new += f"Sent from {message_sent["author_name"]} at {message_sent["timestamp"]}: {message_sent["content"]}\n"

                for message_sent in reversed(self.active_channel_oldest):
                    conv_old += f"Sent from {message_sent["author_name"]} at {message_sent["timestamp"]}: {message_sent["content"]}\n"

                ## we get the summary of the conversation
                summary_conv = gemini_conv_summarizer(conversation=conv_old)
                ## we get the claim that we want to fact check
                claim = clean_content.replace(self.bot.user.mention, "").strip()
                ## we give the fact checker the different data
                fact_checking = gemini_checker(facts=claim, context=summary_conv, conversation=conv_new)
                ## the bot then replies with fact
                bot_response = await message.channel.send(fact_checking)

                ## get the metadata for the message
                bot_metadata = {
            "author_id" : bot_response.author.id,
            "author_name" : bot_response.author.global_name,
            "content" : bot_response.content,
            "timestamp": bot_response.created_at
            }
                self.active_channel_newest.insert(0,bot_metadata)

class DailyNewsSummaryCog(commands.Cog):
## to test the task
    def __init__(self, bot):
        self.bot = bot
        ## we get the channel ids for every news channel
        self.channel_ids = [1402738419297423371, 1402738930952179783, 
               1402739554217230406, 1402741889345650899,
               1402742273569194084, 1402743156805468231,
               1402747455103303862, 1413453438263758868,
               1402747259564589076, 1402746900850938006,
               1402743693991088229]
        self.task_test.start()

    def cog_unload(self):
        ## here we do this to stop the task when we reload to not have multiple orphan tasks
        return self.task_test.cancel()
    
    ## here we will define the function for the list of tasks to perform

    async def deliver_news(self, channel_id):
        ## here we get channel
        channel = self.bot.get_channel(channel_id)
        ## here we get the channel topic
        channel_topic = channel.topic
        ## here we make sure the channel is found
        ## we will get a simple code because we are the one gathering the channel ids
        news_summary = gemini_news(topic=channel_topic, date=datetime.datetime.now().date())   
        ## here we send the news
        await channel.send(news_summary)
        print(f"The news was delivered to channel: {channel.name}")
            
    ## we put a task loop
    @tasks.loop(hours=21, minutes=3, seconds=0)
    async def task_test(self):
        ## here we provide the channel ids for sending the news 
        task = []

        for ids in self.channel_ids:
            t = self.deliver_news(channel_id=ids)
            task.append(t)

        ## after gethering the tasks we get the cycle to work
        if task:
            await asyncio.gather(*task, return_exceptions=True)

        print("Finished!")


    


    @task_test.before_loop
    async def printer(self):
        print("waiting...\n")
        await self.bot.wait_until_ready()
        print("Bot is ready!\n")

    @task_test.after_loop
    async def end_news(self):
        print("The news was delivered!")




# ## here we are going to log in

@saiba_ears.event
async def on_ready():
    print(f"logging into the server...")
    print(f"logged in as {saiba_ears.user}")
    print(f"ready to go!")




async def main():
    # this is the line that registers your cog
    await saiba_ears.add_cog(ThreadDiscussionCog(saiba_ears))
    await saiba_ears.add_cog(DiscussionCog(saiba_ears))
    await saiba_ears.add_cog(FactCheckerCog(saiba_ears))
    #await saiba_ears.add_cog(DailyNewsSummaryCog(saiba_ears))
    
    # start the bot using your token
    await saiba_ears.start(DISCORD_TOKEN)

# ---  run the main async function ---
if __name__ == "__main__":
    asyncio.run(main())


    





