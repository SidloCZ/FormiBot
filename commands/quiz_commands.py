import discord
from discord import app_commands, ui
import time
import asyncio
import random
import datetime
import difflib
import json
import os
from typing import Optional

from utils import PaginatorView
from config import (
    QUIZ_QUESTIONS_FILE,
    QUIZ_SUGGESTIONS_FILE,
    QUIZ_ROLE_ID,
    QUIZ_SUGGESTION_CHANNEL_ID,
    MOD_ROLE_IDS
)

APPROVAL_THRESHOLD = 10
SUGGESTION_LIFETIME_DAYS = 3
MIN_SCORE_TO_SUGGEST = 1000

class SuggestionVoteView(ui.View):
    """Interaktivní hlasování o přijetí návrhu otázky bez emoji."""
    def __init__(self, cog_instance: 'QuizCommands', message_id: str):
        super().__init__(timeout=None)
        self.cog = cog_instance
        self.message_id = str(message_id)

    def _get_counts(self):
        suggestion = self.cog.pending_suggestions.get(self.message_id, {})
        upvotes = len(suggestion.get("upvoters", []))
        downvotes = len(suggestion.get("downvoters", []))
        return upvotes, downvotes

    @ui.button(label="Schválit (+1)", style=discord.ButtonStyle.green, custom_id="quiz_suggest_up")
    async def upvote_button(self, interaction: discord.Interaction, button: ui.Button):
        suggestion = self.cog.pending_suggestions.get(self.message_id)
        if not suggestion:
            await interaction.response.send_message("Tento návrh již není aktivní.", ephemeral=True)
            return

        user_id = interaction.user.id
        if "upvoters" not in suggestion:
            suggestion["upvoters"] = []
        if "downvoters" not in suggestion:
            suggestion["downvoters"] = []

        if user_id in suggestion["upvoters"]:
            suggestion["upvoters"].remove(user_id)
            await interaction.response.send_message("Váš kladný hlas byl odebrán.", ephemeral=True)
        else:
            suggestion["upvoters"].append(user_id)
            if user_id in suggestion["downvoters"]:
                suggestion["downvoters"].remove(user_id)
            await interaction.response.send_message("Hlasovali jste pro schválení.", ephemeral=True)

        upvotes_count = len(suggestion["upvoters"])
        self.cog.save_suggestions()

        if upvotes_count >= APPROVAL_THRESHOLD:
            await self.cog.approve_suggestion(self.message_id, interaction.channel)
        else:
            button.label = f"Schválit (+1) [{upvotes_count}]"
            await interaction.message.edit(view=self)

    @ui.button(label="Odmítnout (-1)", style=discord.ButtonStyle.red, custom_id="quiz_suggest_down")
    async def downvote_button(self, interaction: discord.Interaction, button: ui.Button):
        suggestion = self.cog.pending_suggestions.get(self.message_id)
        if not suggestion:
            await interaction.response.send_message("Tento návrh již není aktivní.", ephemeral=True)
            return

        user_id = interaction.user.id
        if "upvoters" not in suggestion:
            suggestion["upvoters"] = []
        if "downvoters" not in suggestion:
            suggestion["downvoters"] = []

        if user_id in suggestion["downvoters"]:
            suggestion["downvoters"].remove(user_id)
            await interaction.response.send_message("Váš záporný hlas byl odebrán.", ephemeral=True)
        else:
            suggestion["downvoters"].append(user_id)
            if user_id in suggestion["upvoters"]:
                suggestion["upvoters"].remove(user_id)
            await interaction.response.send_message("Hlasovali jste proti schválení.", ephemeral=True)

        downvotes_count = len(suggestion["downvoters"])
        self.cog.save_suggestions()
        button.label = f"Odmítnout (-1) [{downvotes_count}]"
        await interaction.message.edit(view=self)


class QuestionSuggestionModal(ui.Modal, title='Návrh nové kvízové otázky'):
    def __init__(self, cog_instance: 'QuizCommands', quiz_type: str, difficulty: str):
        super().__init__(timeout=None)
        self.cog = cog_instance
        self.quiz_type = quiz_type
        self.difficulty = difficulty

        self.question_text = ui.TextInput(
            label="Znění nové otázky",
            style=discord.TextStyle.paragraph,
            placeholder="Napište sem celou otázku...",
            required=True
        )
        self.add_item(self.question_text)

        self.answers_text = ui.TextInput(
            label="Správné odpovědi (oddělené čárkou)",
            placeholder="např. odpověď 1, odpověď 2, ...",
            required=True
        )
        self.add_item(self.answers_text)

        self.points_text = ui.TextInput(
            label="Počet bodů za správnou odpověď",
            placeholder="např. 25",
            required=True
        )
        self.add_item(self.points_text)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            points = int(self.points_text.value)
            if (self.difficulty == "lehká" and not (10 <= points <= 30)) or \
               (self.difficulty == "střední" and not (40 <= points <= 60)) or \
               (self.difficulty == "těžká" and not (70 <= points <= 90)):
                await interaction.response.send_message(
                    f"Počet bodů ({points}) neodpovídá zvolené obtížnosti „{self.difficulty.capitalize()}“. Zkuste to prosím znovu.",
                    ephemeral=True
                )
                return
        except ValueError:
            await interaction.response.send_message("Počet bodů musí být celé číslo. Zkuste to prosím znovu.", ephemeral=True)
            return

        quiz_role = interaction.guild.get_role(QUIZ_ROLE_ID) if interaction.guild else None
        answers = [ans.strip() for ans in self.answers_text.value.split(',') if ans.strip()]

        embed = discord.Embed(
            title="Nový návrh na kvízovou otázku",
            description=f"Uživatel {interaction.user.mention} navrhl novou otázku.",
            color=discord.Color.orange()
        )
        embed.add_field(name="Typ", value=self.quiz_type.capitalize(), inline=True)
        embed.add_field(name="Obtížnost", value=self.difficulty.capitalize(), inline=True)
        embed.add_field(name="Body", value=str(points), inline=True)
        embed.add_field(name="Otázka", value=self.question_text.value, inline=False)
        embed.add_field(name="Odpovědi", value="||`" + "`, `".join(answers) + "`||", inline=False)
        embed.set_footer(text=f"Pro schválení je potřeba {APPROVAL_THRESHOLD} hlasů pro schválení. Návrh vyprší za {SUGGESTION_LIFETIME_DAYS}&nbsp;dny.")
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)

        await interaction.response.send_message("Děkujeme za návrh. Byl odeslán ke schválení.", ephemeral=True)
        
        suggestion_message = await interaction.channel.send(
            content=quiz_role.mention if quiz_role else "",
            embed=embed
        )

        suggestion_data = {
            "author_id": interaction.user.id,
            "channel_id": interaction.channel.id,
            "timestamp": suggestion_message.created_at.isoformat(),
            "upvoters": [],
            "downvoters": [],
            "question_data": {
                "type": self.quiz_type,
                "difficulty": self.difficulty,
                "question": self.question_text.value,
                "answer": answers,
                "points": points
            }
        }
        
        msg_id_str = str(suggestion_message.id)
        self.cog.pending_suggestions[msg_id_str] = suggestion_data
        self.cog.save_suggestions()

        view = SuggestionVoteView(self.cog, msg_id_str)
        await suggestion_message.edit(view=view)


class SuggestionSetupView(ui.View):
    def __init__(self, cog_instance: 'QuizCommands'):
        super().__init__(timeout=180)
        self.cog = cog_instance
        self.selected_type = None
        self.selected_difficulty = None

        self.type_select = ui.Select(
            placeholder="Vyberte typ kvízu...",
            options=[
                discord.SelectOption(label="Mravenci", value="mravenci"),
                discord.SelectOption(label="Hmyz", value="hmyz"),
                discord.SelectOption(label="Obecný", value="obecny"),
            ],
            custom_id="suggest_type"
        )
        self.type_select.callback = self.on_type_select
        self.add_item(self.type_select)

        self.difficulty_select = ui.Select(
            placeholder="Vyberte obtížnost...",
            options=[
                discord.SelectOption(label="Lehká (10–30 bodů)", value="lehká"),
                discord.SelectOption(label="Střední (40–60 bodů)", value="střední"),
                discord.SelectOption(label="Těžká (70–90 bodů)", value="těžká"),
            ],
            custom_id="suggest_difficulty"
        )
        self.difficulty_select.callback = self.on_difficulty_select
        self.add_item(self.difficulty_select)

        self.continue_button = ui.Button(label="Pokračovat k zadání otázky", style=discord.ButtonStyle.green, custom_id="suggest_continue", disabled=True)
        self.continue_button.callback = self.on_continue
        self.add_item(self.continue_button)

    async def on_type_select(self, interaction: discord.Interaction):
        self.selected_type = interaction.data['values'][0]
        self.check_if_ready()
        await interaction.response.edit_message(view=self)

    async def on_difficulty_select(self, interaction: discord.Interaction):
        self.selected_difficulty = interaction.data['values'][0]
        self.check_if_ready()
        await interaction.response.edit_message(view=self)

    def check_if_ready(self):
        if self.selected_type and self.selected_difficulty:
            self.continue_button.disabled = False

    async def on_continue(self, interaction: discord.Interaction):
        if not self.selected_type or not self.selected_difficulty:
            await interaction.response.send_message("Musíte vybrat typ i obtížnost.", ephemeral=True)
            return
        
        modal = QuestionSuggestionModal(self.cog, self.selected_type, self.selected_difficulty)
        await interaction.response.send_modal(modal)
        
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)


class QuizSelectionView(discord.ui.View):
    def __init__(self, cog_instance: 'QuizCommands'):
        super().__init__(timeout=180)
        self.cog = cog_instance
        self.quiz_questions_data = self.cog.quiz_questions
        self.selected_type = None
        self.selected_difficulty = None

        quiz_type_options = [discord.SelectOption(label=quiz_type.capitalize(), value=quiz_type) for quiz_type in self.quiz_questions_data.keys()]
        self.quiz_type_select = discord.ui.Select(
            placeholder="Vyberte typ kvízu...",
            options=quiz_type_options if quiz_type_options else [discord.SelectOption(label="Žádné", value="none")],
            custom_id="quiz_type_select"
        )
        self.add_item(self.quiz_type_select)
        self.quiz_type_select.callback = self.on_quiz_type_select

        self.start_button = discord.ui.Button(label="Spustit kvíz", style=discord.ButtonStyle.green, custom_id="start_quiz_button", disabled=True)
        self.add_item(self.start_button)
        self.start_button.callback = self.on_start_button

        self.random_quiz_button = ui.Button(label="Náhodný kvíz", style=discord.ButtonStyle.grey, custom_id="random_quiz_button", disabled=False)
        self.add_item(self.random_quiz_button)
        self.random_quiz_button.callback = self.on_random_quiz_button

    async def on_quiz_type_select(self, interaction: discord.Interaction):
        self.selected_type = interaction.data['values'][0]
        
        difficulty_options = []
        if self.selected_type in self.quiz_questions_data:
            difficulty_keys = list(self.quiz_questions_data[self.selected_type].keys())
            for difficulty in difficulty_keys:
                difficulty_options.append(discord.SelectOption(label=difficulty.capitalize(), value=difficulty))
        
        for item in self.children[:]:
            if isinstance(item, discord.ui.Select) and item.custom_id == "quiz_difficulty_select":
                self.remove_item(item)
        
        self.quiz_difficulty_select = ui.Select(
            placeholder="Vyberte obtížnost...",
            options=difficulty_options if difficulty_options else [discord.SelectOption(label="Žádná", value="none")],
            custom_id="quiz_difficulty_select",
            disabled=False
        )
        self.quiz_difficulty_select.callback = self.on_quiz_difficulty_select
        self.add_item(self.quiz_difficulty_select)
        
        self.children.sort(key=lambda x: 0 if isinstance(x, ui.Select) else 1)
        await interaction.response.edit_message(view=self)

    async def on_quiz_difficulty_select(self, interaction: discord.Interaction):
        self.selected_difficulty = interaction.data['values'][0]
        self.start_button.disabled = False
        await interaction.response.edit_message(view=self)

    async def on_start_button(self, interaction: discord.Interaction):
        if self.cog.quiz_active:
            await interaction.response.send_message("Kvíz již probíhá. Počkejte prosím, až skončí aktuální kvíz.", ephemeral=True)
            return

        if not self.selected_type or not self.selected_difficulty:
            await interaction.response.send_message("Prosím, vyberte typ a obtížnost kvízu.", ephemeral=True)
            return
        
        selected_questions = self.cog.quiz_questions.get(self.selected_type, {}).get(self.selected_difficulty, {})
        
        if not selected_questions:
            await interaction.response.send_message(f"Pro typ „{self.selected_type}“ a obtížnost „{self.selected_difficulty}“ nejsou k dispozici žádné otázky.", ephemeral=True)
            return

        self.cog.quiz_active = True
        self.cog.active_quiz_channel = interaction.channel
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content=f"Spouštím kvíz: **{self.selected_type.capitalize()} – {self.selected_difficulty.capitalize()}**.", view=self)
        
        announcement_channel = interaction.channel
        quiz_role = interaction.guild.get_role(QUIZ_ROLE_ID) if interaction.guild else None
        if (time.time() - self.cog.last_quiz_start_message_time) >= 10800:
            await announcement_channel.send(f"Byl spuštěn kvíz: **{self.selected_type.capitalize()} – {self.selected_difficulty.capitalize()}**. {quiz_role.mention if quiz_role else ''} připojte se a ukažte své znalosti.")
            self.cog.last_quiz_start_message_time = time.time()

        try:
            await self.run_quiz(interaction.channel, selected_questions, self.selected_type)
        finally:
            self.cog.quiz_active = False
            self.cog.active_quiz_channel = None
            self.cog.current_quiz_question_data = None

    async def on_random_quiz_button(self, interaction: discord.Interaction):
        if self.cog.quiz_active:
            await interaction.response.send_message("Kvíz již probíhá. Počkejte prosím, až skončí aktuální kvíz.", ephemeral=True)
            return

        if not self.cog.quiz_questions:
            await interaction.response.send_message("Kvíz nelze spustit, chybí otázky.", ephemeral=True)
            return

        random_type = random.choice(list(self.cog.quiz_questions.keys()))
        random_difficulty = random.choice(list(self.cog.quiz_questions[random_type].keys()))
        selected_questions = self.cog.quiz_questions.get(random_type, {}).get(random_difficulty, {})
        
        if not selected_questions:
            await interaction.response.send_message(f"Pro náhodně vybraný typ „{random_type}“ a obtížnost „{random_difficulty}“ nejsou k dispozici žádné otázky.", ephemeral=True)
            return

        self.cog.quiz_active = True
        self.cog.active_quiz_channel = interaction.channel
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content=f"Spouštím náhodný kvíz: **{random_type.capitalize()} – {random_difficulty.capitalize()}**.", view=self)
        
        announcement_channel = interaction.channel
        quiz_role = interaction.guild.get_role(QUIZ_ROLE_ID) if interaction.guild else None
        if (time.time() - self.cog.last_quiz_start_message_time) >= 1200:
            await announcement_channel.send(f"Byl spuštěn náhodný kvíz: **{random_type.capitalize()} – {random_difficulty.capitalize()}**. {quiz_role.mention if quiz_role else ''} připojte se a ukažte své znalosti.")
            self.cog.last_quiz_start_message_time = time.time()

        try:
            await self.run_quiz(interaction.channel, selected_questions, random_type)
        finally:
            self.cog.quiz_active = False
            self.cog.active_quiz_channel = None
            self.cog.current_quiz_question_data = None

    async def run_quiz(self, channel: discord.TextChannel, questions_data: dict, quiz_type: str):
        current_week = str(datetime.datetime.now(datetime.timezone.utc).isocalendar().week)
        questions = list(questions_data.items())
        random.shuffle(questions)
        question_count = 0
        unanswered_consecutive_count = 0

        for question, data in questions:
            if question_count >= 10 or unanswered_consecutive_count >= 3:
                break
            
            self.cog.current_quiz_question_data = {"question": question, "answers": data["answer"]}
            await channel.send(f"**Otázka:** {question}")
            possible_answers = data["answer"]
            points = data["points"]
            
            answered_correctly_this_round = False
            incorrect_responders = set()
            start_time = time.time()
            QUIZ_TIMEOUT = 30.0

            while time.time() - start_time < QUIZ_TIMEOUT:
                try:
                    remaining_time = QUIZ_TIMEOUT - (time.time() - start_time)
                    if remaining_time <= 0:
                        break

                    message = await self.cog.client.wait_for(
                        'message',
                        timeout=remaining_time,
                        check=lambda msg: msg.channel == channel and not msg.author.bot
                    )
                    
                    user_id = str(message.author.id)
                    user_answer_lower = message.content.lower().strip()
                    
                    is_correct = False
                    for correct_ans in possible_answers:
                        similarity = difflib.SequenceMatcher(None, user_answer_lower, correct_ans.lower().strip()).ratio()
                        if similarity >= 0.83:
                            is_correct = True
                            break
                    
                    if is_correct:
                        time_taken = time.time() - start_time
                        gained_points = max(1, round(points - (time_taken / 2)))

                        old_overall_score = self.cog.scores["total_scores"].get(user_id, {}).get("overall", 0)

                        if user_id not in self.cog.scores["total_scores"]:
                            self.cog.scores["total_scores"][user_id] = {"overall": 0, "hints": 0}
                        if quiz_type not in self.cog.scores["total_scores"][user_id]:
                            self.cog.scores["total_scores"][user_id][quiz_type] = 0
                        if "hints" not in self.cog.scores["total_scores"][user_id]:
                            self.cog.scores["total_scores"][user_id]["hints"] = 0

                        self.cog.scores["total_scores"][user_id]["overall"] += gained_points
                        self.cog.scores["total_scores"][user_id][quiz_type] += gained_points
                        
                        new_overall_score = self.cog.scores["total_scores"][user_id]["overall"]
                        hints_earned_this_turn = (new_overall_score // 1000) - (old_overall_score // 1000)
                        
                        if hints_earned_this_turn > 0:
                            current_hints = self.cog.scores["total_scores"][user_id]["hints"]
                            self.cog.scores["total_scores"][user_id]["hints"] = min(3, current_hints + hints_earned_this_turn)
                            if self.cog.scores["total_scores"][user_id]["hints"] > current_hints:
                                await channel.send(f"{message.author.mention}, získal jsi {self.cog.scores['total_scores'][user_id]['hints'] - current_hints} nápověd. Celkem máš {self.cog.scores['total_scores'][user_id]['hints']} nápověd (max 3).")

                        if current_week not in self.cog.scores["weekly_scores"]:
                            self.cog.scores["weekly_scores"][current_week] = {}
                        if user_id not in self.cog.scores["weekly_scores"][current_week]:
                            self.cog.scores["weekly_scores"][current_week][user_id] = {"overall": 0}
                        if quiz_type not in self.cog.scores["weekly_scores"][current_week][user_id]:
                            self.cog.scores["weekly_scores"][current_week][user_id][quiz_type] = 0

                        self.cog.scores["weekly_scores"][current_week][user_id]["overall"] += gained_points
                        self.cog.scores["weekly_scores"][current_week][user_id][quiz_type] += gained_points
                        
                        await channel.send(
                            f'Správně, {message.author.mention}. Získal jsi **{gained_points}** bodů. '
                            f'Celkem tento týden (**{quiz_type.capitalize()}**): **{self.cog.scores["weekly_scores"][current_week][user_id].get(quiz_type, 0)}**.'
                        )
                        answered_correctly_this_round = True
                        unanswered_consecutive_count = 0
                        break
                    else:
                        if message.author.id not in incorrect_responders:
                            await channel.send(f'To není správná odpověď, {message.author.mention}. Zkus to znovu.')
                            incorrect_responders.add(message.author.id)
                except asyncio.TimeoutError:
                    break
            
            if not answered_correctly_this_round:
                unanswered_consecutive_count += 1
                await channel.send('Čas vypršel. Nikdo neodpověděl správně.')
            
            question_count += 1
            self.cog.current_quiz_question_data = None
            
        await channel.send("Kvíz je u konce. Děkuji za účast.")
        self.cog.save_scores()


class QuizCommands:
    def __init__(self, client: discord.Client, tree: app_commands.CommandTree, scores: dict, save_scores: callable, quiz_questions: dict):
        self.client = client
        self.tree = tree
        self.scores = scores
        self.save_scores = save_scores
        self.quiz_questions = quiz_questions
        self.pending_suggestions = {}

        self.quiz_active = False
        self.active_quiz_channel = None
        self.current_quiz_question_data = None
        self.last_quiz_start_message_time = 0

        self.load_suggestions()
        self.register_commands()
        
        self.client.loop.create_task(self.check_expired_suggestions())

    def load_suggestions(self):
        try:
            with open(QUIZ_SUGGESTIONS_FILE, 'r', encoding='utf-8') as f:
                self.pending_suggestions = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.pending_suggestions = {}

    def save_suggestions(self):
        try:
            with open(QUIZ_SUGGESTIONS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.pending_suggestions, f, indent=4, ensure_ascii=False)
        except IOError as e:
            print(f"Chyba při ukládání návrhů: {e}")

    def save_quiz_questions(self):
        try:
            with open(QUIZ_QUESTIONS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.quiz_questions, f, indent=4, ensure_ascii=False)
        except IOError as e:
            print(f"Chyba při ukládání kvízových otázek: {e}")

    def get_server_stats(self):
        user_ants = getattr(self.client, 'user_ants', {})
        total_users_with_ants = len(user_ants)
        total_ant_types_across_all_users = sum(len(ants) for ants in user_ants.values())
        total_score = sum(user_data.get("overall", 0) for user_data in self.scores["total_scores"].values())
        return total_users_with_ants, total_ant_types_across_all_users, total_score

    def check_if_moderator(self, interaction: discord.Interaction) -> bool:
        mod_role_names = ["Trubec - mod", "Královna - ultra mod", "Antkeeper - ADMIN", "Samec - mod na zkoušku", "Královna - moderátor"]
        if not isinstance(interaction.user, discord.Member):
            return False
        return any(role.id in MOD_ROLE_IDS or role.name in mod_role_names for role in interaction.user.roles)

    async def approve_suggestion(self, message_id_str: str, channel: discord.TextChannel):
        if message_id_str not in self.pending_suggestions:
            return
        suggestion = self.pending_suggestions.pop(message_id_str)
        q_data = suggestion["question_data"]
        author_id = suggestion["author_id"]

        q_type = q_data["type"]
        q_difficulty = q_data["difficulty"]
        q_text = q_data["question"]

        if q_type not in self.quiz_questions:
            self.quiz_questions[q_type] = {}
        if q_difficulty not in self.quiz_questions[q_type]:
            self.quiz_questions[q_type][q_difficulty] = {}
            
        self.quiz_questions[q_type][q_difficulty][q_text] = {
            "answer": q_data["answer"],
            "points": q_data["points"]
        }

        self.save_quiz_questions()
        self.save_suggestions()

        try:
            message = await channel.fetch_message(int(message_id_str))
            approved_embed = discord.Embed(
                title="Návrh schválen a přidán do kvízu",
                description=f"Návrh od uživatele <@{author_id}> byl schválen a přidán do databáze.",
                color=discord.Color.green()
            )
            approved_embed.add_field(name="Otázka", value=q_text, inline=False)
            await message.edit(embed=approved_embed, view=None)
        except Exception as e:
            print(f"Chyba při aktualizaci schválené zprávy návrhu {message_id_str}: {e}")

        author_user = self.client.get_user(author_id)
        if author_user:
            await channel.send(f"Gratuluji, {author_user.mention}. Tvůj návrh kvízové otázky byl schválen a přidán do kvízu.")

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.channel_id != QUIZ_SUGGESTION_CHANNEL_ID:
            return
        if self.client.user and payload.user_id == self.client.user.id:
            return
        message_id_str = str(payload.message_id)
        if message_id_str not in self.pending_suggestions:
            return

        channel = self.client.get_channel(payload.channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        try:
            message = await channel.fetch_message(payload.message_id)
            for reaction in message.reactions:
                if reaction.count >= APPROVAL_THRESHOLD:
                    await self.approve_suggestion(message_id_str, channel)
                    break
        except discord.NotFound:
            self.pending_suggestions.pop(message_id_str, None)
            self.save_suggestions()
        except Exception as e:
            print(f"Chyba při zpracování reakce na návrh {message_id_str}: {e}")

    async def check_expired_suggestions(self):
        await self.client.wait_until_ready()
        while not self.client.is_closed():
            now = datetime.datetime.now(datetime.timezone.utc)
            expiration_delta = datetime.timedelta(days=SUGGESTION_LIFETIME_DAYS)
            
            for message_id_str in list(self.pending_suggestions.keys()):
                suggestion = self.pending_suggestions[message_id_str]
                timestamp = datetime.datetime.fromisoformat(suggestion["timestamp"])
                author_id = suggestion["author_id"]
                
                if now - timestamp > expiration_delta:
                    try:
                        channel_id = suggestion.get("channel_id")
                        if channel_id:
                            channel = self.client.get_channel(channel_id)
                            if channel and isinstance(channel, discord.TextChannel):
                                message = await channel.fetch_message(int(message_id_str))
                                expired_embed = discord.Embed(
                                    title="Návrh zamítnut (expirován)",
                                    description=f"Návrh od <@{author_id}> nezískal dostatečný počet hlasů v časovém limitu.",
                                    color=discord.Color.red()
                                )
                                await message.edit(embed=expired_embed, view=None)

                                author_user = self.client.get_user(author_id)
                                if author_user:
                                    await channel.send(f"Je nám líto, {author_user.mention}. Tvůj návrh kvízové otázky expiroval a byl zamítnut, protože nezískal dostatek hlasů.")

                        self.pending_suggestions.pop(message_id_str, None)
                        self.save_suggestions()
                    except discord.NotFound:
                        self.pending_suggestions.pop(message_id_str, None)
                        self.save_suggestions()
                    except Exception as e:
                        print(f"Chyba při odstraňování expirovaného návrhu {message_id_str}: {e}")

            await asyncio.sleep(60 * 60 * 6)

    def register_commands(self):
        @self.tree.command(name="kviz", description="Spustí vědomostní kvíz s výběrem typu a obtížnosti.")
        async def kviz(interaction: discord.Interaction):
            if self.quiz_active:
                await interaction.response.send_message("Kvíz již probíhá. Počkejte prosím, až skončí aktuální kvíz.", ephemeral=True)
                return

            if not self.quiz_questions:
                await interaction.response.send_message("Kvíz nelze spustit, chybí otázky.", ephemeral=True)
                return

            view = QuizSelectionView(self)
            await interaction.response.send_message("Vyberte typ a obtížnost kvízu:", view=view)

        @self.tree.command(name="navrh_otazky", description="Navrhni novou otázku do kvízu (vyžaduje 1000 bodů).")
        async def navrh_otazky(interaction: discord.Interaction):
            user_id = str(interaction.user.id)
            user_score = self.scores.get("total_scores", {}).get(user_id, {}).get("overall", 0)

            if user_score < MIN_SCORE_TO_SUGGEST:
                await interaction.response.send_message(f"Pro navrhování otázek potřebuješ alespoň **{MIN_SCORE_TO_SUGGEST}**&nbsp;bodů. Tvé aktuální skóre je **{user_score}**.", ephemeral=True)
                return
            
            view = SuggestionSetupView(self)
            await interaction.response.send_message("Nejprve vyberte typ a obtížnost pro vaši novou otázku:", view=view, ephemeral=True)

        @self.tree.command(name="napoveda", description="Použije nápovědu k odhalení odpovědi v kvízu. Získává se za 1000 bodů (max 3).")
        async def napoveda(interaction: discord.Interaction):
            user_id = str(interaction.user.id)

            if not self.quiz_active or self.active_quiz_channel != interaction.channel:
                await interaction.response.send_message("Momentálně neprobíhá žádný aktivní kvíz v tomto kanále.", ephemeral=True)
                return

            if self.current_quiz_question_data is None:
                await interaction.response.send_message("Momentálně není aktivní žádná otázka.", ephemeral=True)
                return

            user_data = self.scores["total_scores"].get(user_id, {})
            hints_available = user_data.get("hints", 0)

            if hints_available < 1:
                await interaction.response.send_message("Nemáš žádné nápovědy k dispozici.", ephemeral=True)
                return

            self.scores["total_scores"][user_id]["hints"] -= 1
            self.save_scores()

            question = self.current_quiz_question_data["question"]
            answers = self.current_quiz_question_data["answers"]
            revealed_answer = random.choice(answers)

            await interaction.response.send_message(
                f"{interaction.user.mention}, použil jsi 1 nápovědu. "
                f"Zbývající nápovědy: {self.scores['total_scores'][user_id]['hints']}.\n\n"
                f"**Otázka:** {question}\n"
                f"**Jedna ze správných odpovědí je:** ||{revealed_answer}||"
            )

        @self.tree.command(name="skore", description="Zobrazí tabulku s celkovým skóre a počtem dostupných nápověd.")
        async def skore(interaction: discord.Interaction):
            all_time_scores = self.scores["total_scores"]
            
            if not all_time_scores:
                await interaction.response.send_message("Zatím neexistuje žádné celkové skóre.")
                return

            sorted_scores = sorted(all_time_scores.items(), key=lambda item: item[1].get("overall", 0), reverse=True)
            pages = []
            current_page_fields = []
            MAX_FIELDS_PER_PAGE = 5
            ranks = {0: "#1", 1: "#2", 2: "#3"}

            for i, (user_id, user_data) in enumerate(sorted_scores):
                user = self.client.get_user(int(user_id))
                user_display_name = user.display_name if user else f"Uživatel (ID: {user_id})"
                rank_prefix = ranks.get(i, f"{i + 1}.")
                
                score_details = f"**Celkové Skóre:** {user_data.get('overall', 0)}\n"
                score_details += f"**Nápovědy:** {user_data.get('hints', 0)}\n"
                for quiz_type, score in user_data.items():
                    if quiz_type not in ["overall", "hints"]:
                        score_details += f"- {quiz_type.capitalize()}: {score}\n" 
                
                current_page_fields.append((f"{rank_prefix} {user_display_name}", score_details))

                if len(current_page_fields) == MAX_FIELDS_PER_PAGE or i == len(sorted_scores) - 1:
                    embed = discord.Embed(title="Žebříček (Celkové)", description="Nejlepší uživatelé podle celkového skóre.", color=discord.Color.gold())
                    for name, value in current_page_fields:
                        embed.add_field(name=name, value=value, inline=False)
                    
                    _, _, total_overall_score = self.get_server_stats()
                    average_score = total_overall_score / len(self.scores["total_scores"]) if self.scores["total_scores"] else 0
                    embed.add_field(name="Statistiky serveru", value=f"**Celkem uživatelů v žebříčku:** {len(self.scores['total_scores'])}\n**Průměrné skóre:** {average_score:.2f}", inline=False)
                    embed.set_footer(text=f"Zobrazeno top {len(sorted_scores)}. {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
                    pages.append(embed)
                    current_page_fields = []

            view = PaginatorView(pages, interaction)
            await interaction.response.send_message(embed=pages[0], view=view)
            view.message = await interaction.original_response()

        @self.tree.command(name="skore_tyden", description="Zobrazí tabulku se skóre pro aktuální týden.")
        async def skore_tyden(interaction: discord.Interaction):
            current_week = str(datetime.datetime.now(datetime.timezone.utc).isocalendar().week)
            
            if current_week not in self.scores["weekly_scores"] or not self.scores["weekly_scores"][current_week]:
                await interaction.response.send_message(f"Pro tento týden ({current_week}) zatím neexistuje žádné skóre.")
                return

            weekly_scores = self.scores["weekly_scores"][current_week]
            sorted_scores = sorted(weekly_scores.items(), key=lambda item: item[1].get("overall", 0), reverse=True)

            pages = []
            current_page_fields = []
            MAX_FIELDS_PER_PAGE = 5
            ranks = {0: "#1", 1: "#2", 2: "#3"}

            for i, (user_id, user_data) in enumerate(sorted_scores):
                user = self.client.get_user(int(user_id))
                user_display_name = user.display_name if user else f"Uživatel (ID: {user_id})"
                rank_prefix = ranks.get(i, f"{i + 1}.")
                
                score_details = f"**Týdenní Skóre:** {user_data.get('overall', 0)}\n"
                for quiz_type, score in user_data.items():
                    if quiz_type != "overall":
                        score_details += f"- {quiz_type.capitalize()}: {score}\n" 
                
                current_page_fields.append((f"{rank_prefix} {user_display_name}", score_details))

                if len(current_page_fields) == MAX_FIELDS_PER_PAGE or i == len(sorted_scores) - 1:
                    embed = discord.Embed(title=f"Týdenní žebříček (Týden {current_week})", description="Nejlepší uživatelé za aktuální týden.", color=discord.Color.blue())
                    for name, value in current_page_fields:
                        embed.add_field(name=name, value=value, inline=False)
                    
                    average_weekly_score = sum(ud.get("overall", 0) for ud in weekly_scores.values()) / len(weekly_scores) if weekly_scores else 0
                    embed.add_field(name="Statistiky serveru", value=f"**Celkem uživatelů tento týden:** {len(weekly_scores)}\n**Průměrné týdenní skóre:** {average_weekly_score:.2f}", inline=False)
                    embed.set_footer(text=f"Zobrazeno top {len(sorted_scores)}. {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
                    pages.append(embed)
                    current_page_fields = []

            view = PaginatorView(pages, interaction)
            await interaction.response.send_message(embed=pages[0], view=view)
            view.message = await interaction.original_response()

        upravit_skore_group = app_commands.Group(name="upravit_skore", description="Správa skóre (jen pro mody).")

        @upravit_skore_group.command(name="nastavit", description="Nastaví celkové skóre uživatele.")
        @app_commands.describe(uzivatel="Uživatel", body="Nová hodnota skóre.")
        async def upravit_skore_nastavit(interaction: discord.Interaction, uzivatel: discord.Member, body: int):
            if not self.check_if_moderator(interaction):
                await interaction.response.send_message("K tomuto příkazu nemáš oprávnění.", ephemeral=True)
                return
            user_id = str(uzivatel.id)
            if user_id not in self.scores["total_scores"]:
                self.scores["total_scores"][user_id] = {"overall": 0, "hints": 0}
            self.scores["total_scores"][user_id]["overall"] = body
            self.save_scores()
            await interaction.response.send_message(f'Celkové skóre uživatele {uzivatel.mention} bylo nastaveno na {body}.')

        @upravit_skore_group.command(name="smazat", description="Vymaže skóre uživatele (nebo všech).")
        @app_commands.describe(uzivatel="Uživatel (nech prázdné pro všechny).")
        async def upravit_skore_smazat(interaction: discord.Interaction, uzivatel: Optional[discord.Member] = None):
            if not self.check_if_moderator(interaction):
                await interaction.response.send_message("K tomuto příkazu nemáš oprávnění.", ephemeral=True)
                return
            if uzivatel:
                user_id = str(uzivatel.id)
                if user_id in self.scores["total_scores"]:
                    del self.scores["total_scores"][user_id]
                    for week_data in self.scores["weekly_scores"].values():
                        if user_id in week_data:
                            del week_data[user_id]
                    await interaction.response.send_message(f'Skóre uživatele {uzivatel.mention} bylo vymazáno.')
                else:
                    await interaction.response.send_message(f'Uživatel {uzivatel.mention} nemá žádné skóre.', ephemeral=True)
            else:
                self.scores["total_scores"].clear()
                self.scores["weekly_scores"].clear()
                await interaction.response.send_message('Všechna skóre byla vymazána.')
            self.save_scores()
        
        self.tree.add_command(upravit_skore_group)
