import discord
from discord.ext import commands, tasks
import os
import json
import colorsys
from discord.ui import Button, View, Modal, TextInput, Select
from discord.app_commands import describe
from discord.ext import commands, tasks
from dotenv import load_dotenv
from keep_alive import keep_alive
import asyncio
import random
from datetime import datetime, timedelta

load_dotenv()
token = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True
bot = commands.Bot(command_prefix='+', intents=intents)

webhooks_perso = {}
sanctions = []
rainbow_roles = {}
bot_data = {}
giveaways = {}
log_channels = {}
join_messages = {}
# Ajout pour le système d'autorôle
REACTION_MESSAGE_ID = None
EMOJI_TO_ROLE = {}

DATA_FILE = "bot_data.json"
MUTE_ROLE_NAME = "Muted"

def save_data(data):
    try:
        os.makedirs(os.path.dirname(DATA_FILE) or '.', exist_ok=True)
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=4)
        print("Données sauvegardées avec succès.")
    except Exception as e:
        print(f"Erreur lors de la sauvegarde des données : {e}")

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                content = f.read()
                if content:
                    data = json.loads(content)
                    print("Données chargées avec succès.")
                    return data
                else:
                    print("Le fichier de données est vide. Initialisation des données.")
        except json.JSONDecodeError as e:
            print(f"Erreur de décodage JSON lors du chargement : {e}")
        except Exception as e:
            print(f"Erreur lors du chargement des données : {e}")
    
    print("Fichier de données non trouvé ou erreur. Création de données par défaut.")
    return {"ticket_panels": [], "ticket_logs": {}, "log_channels": {}, "join_messages": {}}

def chunk_text(text, chunk_size=1900):
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

async def handle_claim_ticket(interaction: discord.Interaction):
    channel = interaction.channel
    if not channel.name.startswith("ticket-"):
        await interaction.response.send_message("Ce bouton ne peut être utilisé que dans un ticket.", ephemeral=True)
        return
    if "Pris en charge" in channel.topic:
        await interaction.response.send_message("Ce ticket a déjà été réclamé.", ephemeral=True)
        return
    new_topic = channel.topic + f" | Pris en charge par {interaction.user.name}"
    await channel.edit(topic=new_topic)
    await interaction.response.send_message(f"Le ticket a été réclamé par {interaction.user.mention}.", ephemeral=False)

async def handle_reopen_ticket(interaction: discord.Interaction):
    channel = interaction.channel
    if not channel.name.startswith("closed-"):
        await interaction.response.send_message("Ce ticket n'est pas fermé.", ephemeral=True)
        return
    try:
        ticket_creator_id_str = channel.topic.split('(ID: ')[1].split(')')[0]
        ticket_creator = interaction.guild.get_member(int(ticket_creator_id_str))
    except (IndexError, ValueError):
        ticket_creator = None
    if ticket_creator:
        await channel.edit(name=channel.name.replace("closed-", ""))
        await channel.set_permissions(ticket_creator, view_channel=True, send_messages=True)
        await interaction.response.send_message(f"Le ticket a été réouvert par {interaction.user.mention}.", ephemeral=False)
    else:
        await interaction.response.send_message("Impossible de retrouver le créateur du ticket. Le salon a été réouvert, mais les permissions n'ont pas été ajustées.", ephemeral=True)

async def handle_save_and_delete_ticket(interaction: discord.Interaction):
    await interaction.response.defer()
    channel = interaction.channel
    log_channel_id = bot_data["ticket_logs"].get(str(interaction.guild.id))
    if not log_channel_id:
        await interaction.followup.send("Le salon de logs n'a pas été défini. Le ticket va être supprimé sans être sauvegardé.", ephemeral=True)
        await channel.delete()
        return
    log_channel = interaction.guild.get_channel(int(log_channel_id))
    if not log_channel:
        await interaction.followup.send("Le salon de logs n'existe plus. Le ticket va être supprimé sans être sauvegardé.", ephemeral=True)
        await channel.delete()
        return
    log_messages = []
    async for message in channel.history(limit=None, oldest_first=True):
        log_messages.append(f"[{message.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {message.author.name}: {message.content}")
    log_content = "\n".join(log_messages)
    chunks = chunk_text(log_content)
    await log_channel.send(f"**Logs pour le ticket de {channel.topic.split('(ID: ')[0].strip()}**")
    for chunk in chunks:
        await log_channel.send(f"```\n{chunk}\n```")
    await interaction.followup.send("Logs sauvegardés. Suppression du ticket en cours...", ephemeral=True)
    await channel.delete()

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f'Connecté en tant que {bot.user}')
    print('Le bot est prêt à utiliser les commandes slash.')
    global bot_data, log_channels, join_messages
    bot_data = load_data()
    log_channels = bot_data.get("log_channels", {})
    join_messages = bot_data.get("join_messages", {})
    for panel in bot_data.get("ticket_panels", []):
        view = TicketView(
            category_id=panel['category_id'],
            roles_ping_ids=panel['roles_ping_ids'],
            mode=panel['mode'],
            roles_visibles_ids=panel['roles_visibles_ids'],
            selector_content=panel.get('selector_content')
        )
        bot.add_view(view)

@bot.event
async def on_member_join(member):
    guild_id = str(member.guild.id)
    if guild_id in join_messages:
        message_config = join_messages[guild_id]
        embed = discord.Embed(
            title=message_config.get("title", "Bienvenue !"),
            description=message_config.get("description", "Bienvenue sur le serveur !"),
            color=discord.Color.green()
        )
        support_link = message_config.get("support_link")
        if support_link:
            embed.add_field(name="Besoin d'aide ?", value=f"[Rejoindre le serveur de support]({support_link})", inline=False)
        
        try:
            await member.send(embed=embed)
            print(f"Message de bienvenue envoyé à {member.name}")
        except discord.Forbidden:
            print(f"Impossible d'envoyer un message privé à {member.name}. Les DMs sont désactivés.")
        except Exception as e:
            print(f"Une erreur est survenue lors de l'envoi du message privé à {member.name}: {e}")

@bot.tree.command(name="setup-join-message", description="Configure le message de bienvenue envoyé en MP aux nouveaux membres.")
@describe(
    titre="Le titre de l'embed de bienvenue.",
    description_message="Le contenu du message de bienvenue.",
    lien_support="Le lien du serveur de support (facultatif)."
)
async def setup_join_message(interaction: discord.Interaction, titre: str, description_message: str, lien_support: str = None):
    guild_id = str(interaction.guild.id)
    join_messages[guild_id] = {
        "title": titre,
        "description": description_message,
        "support_link": lien_support
    }
    bot_data["join_messages"] = join_messages
    save_data(bot_data)
    
    await interaction.response.send_message(
        "Le message de bienvenue en MP a été configuré avec succès !",
        ephemeral=True
    )



# =========================
# 🚪 Gestion des membres
# =========================

# Kick
@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="Aucune raison fournie"):
    await member.kick(reason=reason)
    sanctions.append((datetime.now(), f"🚪 {member} exclu par {ctx.author} | Raison : {reason}"))
    await ctx.send(f"🚪 {member.mention} a été exclu. Raison : {reason}")

# Ban
@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="Aucune raison fournie"):
    await member.ban(reason=reason)
    sanctions.append((datetime.now(), f"🔨 {member} banni par {ctx.author} | Raison : {reason}"))
    await ctx.send(f"🔨 {member.mention} a été banni. Raison : {reason}")

# Tempban
@bot.command()
@commands.has_permissions(ban_members=True)
async def tempban(ctx, member: discord.Member, temps: int, *, reason="Aucune raison fournie"):
    await member.ban(reason=reason)
    sanctions.append((datetime.now(), f"⏳ {member} banni {temps}s par {ctx.author} | Raison : {reason}"))
    await ctx.send(f"⏳ {member.mention} a été banni pour {temps} secondes. Raison : {reason}")
    await asyncio.sleep(temps)
    await ctx.guild.unban(member)
    await ctx.send(f"✅ {member.mention} a été débanni après {temps} secondes.")

# Unban
@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, user: str):
    banned_users = await ctx.guild.bans()
    for ban_entry in banned_users:
        if user in (str(ban_entry.user), str(ban_entry.user.id)):
            await ctx.guild.unban(ban_entry.user)
            sanctions.append((datetime.now(), f"♻️ {ban_entry.user} débanni par {ctx.author}"))
            return await ctx.send(f"♻️ {ban_entry.user} a été débanni.")
    await ctx.send("❌ Utilisateur non trouvé dans la liste des bannis.")


# =========================
# 🤐 Gestion des mutes
# =========================

# Mute
@bot.command()
@commands.has_permissions(manage_roles=True)
async def mute(ctx, member: discord.Member, *, reason="Aucune raison fournie"):
    mute_role = discord.utils.get(ctx.guild.roles, name=MUTE_ROLE_NAME)
    if not mute_role:
        mute_role = await ctx.guild.create_role(name=MUTE_ROLE_NAME)
        for channel in ctx.guild.channels:
            await channel.set_permissions(mute_role, send_messages=False, speak=False)
    await member.add_roles(mute_role, reason=reason)
    sanctions.append((datetime.now(), f"🤐 {member} mute par {ctx.author} | Raison : {reason}"))
    await ctx.send(f"🤐 {member.mention} a été mute. Raison : {reason}")

# Tempmute
@bot.command()
@commands.has_permissions(manage_roles=True)
async def tempmute(ctx, member: discord.Member, temps: int, *, reason="Aucune raison fournie"):
    mute_role = discord.utils.get(ctx.guild.roles, name=MUTE_ROLE_NAME)
    if not mute_role:
        mute_role = await ctx.guild.create_role(name=MUTE_ROLE_NAME)
        for channel in ctx.guild.channels:
            await channel.set_permissions(mute_role, send_messages=False, speak=False)
    await member.add_roles(mute_role, reason=reason)
    sanctions.append((datetime.now(), f"⏳ {member} mute {temps}s par {ctx.author} | Raison : {reason}"))
    await ctx.send(f"⏳ {member.mention} a été mute pour {temps} secondes. Raison : {reason}")
    await asyncio.sleep(temps)
    await member.remove_roles(mute_role)
    await ctx.send(f"✅ {member.mention} n'est plus mute.")

# Unmute
@bot.command()
@commands.has_permissions(manage_roles=True)
async def unmute(ctx, member: discord.Member):
    mute_role = discord.utils.get(ctx.guild.roles, name=MUTE_ROLE_NAME)
    if mute_role in member.roles:
        await member.remove_roles(mute_role)
        sanctions.append((datetime.now(), f"♻️ {member} unmute par {ctx.author}"))
        await ctx.send(f"♻️ {member.mention} n'est plus mute.")
    else:
        await ctx.send("❌ Ce membre n'est pas mute.")


# =========================
# 🔒 Gestion des salons
# =========================

# Lock
@bot.command()
@commands.has_permissions(manage_channels=True)
async def lock(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    overwrite = channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = False
    await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    sanctions.append((datetime.now(), f"🔒 {channel} verrouillé par {ctx.author}"))
    await ctx.send(f"🔒 Le salon {channel.mention} est verrouillé.")

# Unlock
@bot.command()
@commands.has_permissions(manage_channels=True)
async def unlock(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    overwrite = channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = None
    await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    sanctions.append((datetime.now(), f"🔓 {channel} déverrouillé par {ctx.author}"))
    await ctx.send(f"🔓 Le salon {channel.mention} est déverrouillé.")


# =========================
# 📜 Liste des sanctions
# =========================

@bot.command()
async def list(ctx):
    if not sanctions:
        return await ctx.send("📂 Aucune sanction enregistrée.")

    embed = discord.Embed(
        title="📜 Dernières sanctions",
        color=discord.Color.red(),
        timestamp=datetime.now()
    )
    for t, s in sanctions[-10:]:
        embed.add_field(
            name=t.strftime("%d/%m %H:%M"),
            value=s,
            inline=False
        )
    await ctx.send(embed=embed)


# =========================
# 🔧 Erreurs de permission
# =========================

@kick.error
@ban.error
@tempban.error
@mute.error
@tempmute.error
@lock.error
@unlock.error
@unban.error
@unmute.error
async def permission_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Tu n’as pas les permissions nécessaires.")
@bot.event
async def on_message_delete(message):
    if message.author.bot:
        return
    
    guild_id = str(message.guild.id)
    if guild_id in log_channels:
        log_channel = bot.get_channel(int(log_channels[guild_id]))
        
        if log_channel:
            embed = discord.Embed(
                title="🗑️ Message supprimé",
                description=f"**Contenu :**\n{message.content}\n\n"
                            f"[Aller au message (Lien masqué)]({message.jump_url})",
                color=discord.Color.red(),
                timestamp=datetime.datetime.now()
            )
            embed.set_author(name=message.author.display_name, icon_url=message.author.avatar.url)
            embed.add_field(name="Salon", value=message.channel.mention, inline=True)
            embed.add_field(name="ID Utilisateur", value=message.author.id, inline=True)
            embed.add_field(name="ID Message", value=message.id, inline=True)
            
            await log_channel.send(embed=embed)

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or before.content == after.content:
        return
    
    guild_id = str(before.guild.id)
    if guild_id in log_channels:
        log_channel = bot.get_channel(int(log_channels[guild_id]))
        
        if log_channel:
            embed = discord.Embed(
                title="✍️ Message modifié",
                description=f"**Ancien contenu :**\n{before.content}\n\n"
                            f"**Nouveau contenu :**\n{after.content}\n\n"
                            f"[Aller au message (Lien masqué)]({after.jump_url})",
                color=discord.Color.orange(),
                timestamp=datetime.datetime.now()
            )
            embed.set_author(name=before.author.display_name, icon_url=before.author.avatar.url)
            embed.add_field(name="Salon", value=before.channel.mention, inline=True)
            embed.add_field(name="ID Utilisateur", value=before.author.id, inline=True)
            embed.add_field(name="ID Message", value=before.id, inline=True)
            
            await log_channel.send(embed=embed)

@bot.event
async def on_command_completion(ctx):
    guild_id = str(ctx.guild.id)
    if guild_id in log_channels:
        channel = bot.get_channel(int(log_channels[guild_id]))
        if channel:
            embed = discord.Embed(
                title="✨ Commande utilisée",
                description=f"**Auteur :** {ctx.author.mention}\n"
                            f"**Salon :** {ctx.channel.mention}\n"
                            f"**Commande :** `{ctx.command.qualified_name}`\n"
                            f"**Arguments :** `{ctx.message.content}`",
                color=discord.Color.purple(),
                timestamp=datetime.datetime.now()
            )
            await channel.send(embed=embed)

async def end_giveaway(message_id, channel_id, winners_count, prize):
    channel = bot.get_channel(channel_id)
    if not channel:
        return
    try:
        message = await channel.fetch_message(message_id)
    except discord.NotFound:
        return
    
    reaction = discord.utils.get(message.reactions, emoji="🎉")
    if not reaction:
        await channel.send("Le giveaway a été annulé (pas de réactions).")
        return

    users = [user async for user in reaction.users() if user != bot.user]
    
    if not users:
        await channel.send(f"Personne n'a participé au giveaway de **{prize}**.")
        return

    if len(users) < winners_count:
        winners_count = len(users)
        await channel.send(f"Pas assez de participants. Seuls {winners_count} gagnants seront tirés au sort.")

    winners = random.sample(users, winners_count)
    winner_mentions = ' '.join([winner.mention for winner in winners])
    
    await channel.send(f"🎉 Le giveaway de **{prize}** est terminé ! 🎉\nFélicitations à {winner_mentions} !")
    
    embed = message.embeds[0]
    embed.title = "🎉 GIVEAWAY TERMINÉ 🎉"
    embed.description = f"**Prix :** {prize}\n**Gagnant(s) :** {winner_mentions}"
    embed.color = discord.Color.gold()
    await message.edit(embed=embed, view=None)

    del giveaways[message_id]

@tasks.loop(seconds=10)
async def check_giveaways():
    now = datetime.datetime.now()
    giveaways_to_end = []
    
    for message_id, data in list(giveaways.items()):
        end_time = data['end_time']
        if now >= end_time:
            giveaways_to_end.append(message_id)

    for message_id in giveaways_to_end:
        data = giveaways[message_id]
        await end_giveaway(message_id, data['channel_id'], data['winners_count'], data['prize'])

@bot.tree.command(name="giveaway", description="Lance un giveaway !")
@describe(duree="Durée du giveaway (ex: 10m, 1h, 1j).", gagnants="Nombre de gagnants.", prix="Le prix à gagner.")
async def create_giveaway(interaction: discord.Interaction, duree: str, gagnants: int, prix: str):
    await interaction.response.defer(ephemeral=True)
    
    if gagnants <= 0:
        await interaction.followup.send("Le nombre de gagnants doit être supérieur à 0.")
        return

    unit = duree[-1]
    value = int(duree[:-1])
    duration_seconds = 0
    if unit == 's':
        duration_seconds = value
    elif unit == 'm':
        duration_seconds = value * 60
    elif unit == 'h':
        duration_seconds = value * 3600
    elif unit == 'j':
        duration_seconds = value * 86400
    else:
        await interaction.followup.send("Format de durée invalide. Utilisez 's', 'm', 'h' ou 'j' (ex: 10m).")
        return

    if duration_seconds <= 0:
      await interaction.followup.send("La durée du giveaway doit être supérieure à zéro.")
      return

    end_time = datetime.datetime.now() + datetime.timedelta(seconds=duration_seconds)
    
    embed = discord.Embed(
        title="🎉 Giveaway 🎉",
        description=f"Réagis avec 🎉 pour participer !\n\n"
                    f"**Prix :** {prix}\n"
                    f"**Gagnant(s) :** {gagnants}\n"
                    f"**Se termine :** <t:{int(end_time.timestamp())}:R>",
        color=0x2E8B57
    )
    embed.set_footer(text=f"Lancé par {interaction.user.display_name} | ID du message: {0}")
    
    giveaway_message = await interaction.channel.send(embed=embed)
    await giveaway_message.add_reaction("🎉")

    embed.set_footer(text=f"Lancé par {interaction.user.display_name} | ID du message: {giveaway_message.id}")
    await giveaway_message.edit(embed=embed)

    giveaways[giveaway_message.id] = {
        'channel_id': interaction.channel.id,
        'winners_count': gagnants,
        'prize': prix,
        'end_time': end_time
    }
    
    await interaction.followup.send("Giveaway lancé avec succès !")
    if not check_giveaways.is_running():
        check_giveaways.start()

@bot.tree.command(name="reroll", description="Relance un giveaway terminé.")
@describe(message_id="L'ID du message du giveaway.", gagnants="Le nombre de nouveaux gagnants (facultatif).")
async def reroll_giveaway(interaction: discord.Interaction, message_id: str, gagnants: int = None):
    await interaction.response.defer(ephemeral=True)

    try:
        original_message = await interaction.channel.fetch_message(int(message_id))
    except discord.NotFound:
        await interaction.followup.send("Message non trouvé. Veuillez vérifier l'ID.")
        return
    
    if not original_message.embeds or "giveaway" not in original_message.embeds[0].title.lower():
        await interaction.followup.send("Ce n'est pas un message de giveaway.")
        return

    try:
        prize = original_message.embeds[0].description.split("**Prix :** ")[1].split("\n")[0].strip()
        reaction = discord.utils.get(original_message.reactions, emoji="🎉")
        users = [user async for user in reaction.users() if user != bot.user]
        
        if not users:
            await interaction.followup.send("Personne n'a participé à ce giveaway.")
            return

        if gagnants is not None:
            winners_count = gagnants
        else:
            winners_count_text = original_message.embeds[0].description.split("**Gagnant(s) :** ")[1].split("\n")[0].strip()
            try:
                winners_count = int(winners_count_text)
            except ValueError:
                winners_count = len(original_message.mentions) if original_message.mentions else 1
                await interaction.followup.send(f"⚠️ Avertissement : Impossible de trouver le nombre de gagnants original. Relance de {winners_count} gagnant(s) par défaut.", ephemeral=True)
        
        if winners_count <= 0:
            winners_count = 1
            await interaction.followup.send(f"Le nombre de gagnants spécifié est invalide. Relance de 1 gagnant par défaut.", ephemeral=True)
        
        new_winners = random.sample(users, min(winners_count, len(users)))
        new_winner_mentions = ' '.join([winner.mention for winner in new_winners])

        await interaction.channel.send(
            f"🎉 Nouveau tirage au sort pour le giveaway de **{prize}** ! 🎉\nFélicitations à {new_winner_mentions} !"
        )
        await interaction.followup.send("Giveaway relancé avec succès !")
        
    except (IndexError, ValueError) as e:
        print(f"Erreur de reroll : {e}")
        await interaction.followup.send("Une erreur est survenue lors du relancement. Le message est peut-être corrompu.")

@bot.tree.command(
    name="get_messages_du_salon",
    description="Récupère et concatène tous les messages d'un salon."
)
@discord.app_commands.describe(salon="Le salon dont il faut lire les messages.")
async def get_messages_command(interaction: discord.Interaction, salon: discord.TextChannel):
    await interaction.response.defer()
    try:
        messages = [message.content async for message in salon.history(limit=None)]
        if not messages:
            await interaction.followup.send(f"Je n'ai pas trouvé de message dans {salon.mention}.")
            return
        messages.reverse()
        messages_concatenees = " ".join(messages)
        message_chunks = chunk_text(messages_concatenees)
        header = f"**Messages de {salon.mention} :**"
        await interaction.followup.send(f"{header}\n```\n{message_chunks[0]}\n```")
        for chunk in message_chunks[1:]:
            await interaction.channel.send(f"```\n{chunk}\n```")
    except discord.Forbidden:
        await interaction.followup.send(f"Je n'ai pas la permission de lire les messages dans {salon.mention}.")
    except Exception as e:
        await interaction.followup.send(f"Une erreur s'est produite : {e}")

@bot.tree.command(
    name="creer-profil-webhook",
    description="Crée un profil de message personnalisé via un webhook avec un nom et un avatar."
)
@discord.app_commands.describe(
    nom_profil="Le nom du profil à créer.",
    salon="Le salon où le webhook sera créé.",
    avatar_url="URL de l'avatar du profil (facultatif)."
)
async def creer_profil_webhook(interaction: discord.Interaction, nom_profil: str, salon: discord.TextChannel, avatar_url: str = None):
    await interaction.response.defer(ephemeral=True)
    if nom_profil in webhooks_perso:
        await interaction.followup.send(f"Un profil nommé `{nom_profil}` existe déjà.")
        return
    try:
        webhook = await salon.create_webhook(name=nom_profil)
        webhooks_perso[nom_profil] = {"webhook": webhook, "avatar_url": avatar_url}
        await interaction.followup.send(f"Le profil `{nom_profil}` a été créé avec succès dans le salon {salon.mention}. Vous pouvez maintenant l'utiliser pour envoyer des messages.")
    except discord.Forbidden:
        await interaction.followup.send("Je n'ai pas la permission de créer de webhooks dans ce salon.")
    except Exception as e:
        await interaction.followup.send(f"Une erreur est survenue lors de la création du webhook : {e}")

async def autocomplete_profils(interaction: discord.Interaction, current: str):
    return [
        discord.app_commands.Choice(name=profil_name, value=profil_name)
        for profil_name in webhooks_perso.keys()
        if current.lower() in profil_name.lower()
    ]

@bot.tree.command(
    name="envoyer-message-profil",
    description="Envoie un message en utilisant un profil personnalisé."
)
@discord.app_commands.describe(
    nom_profil="Le nom du profil à utiliser (choisissez dans la liste).",
    salon_cible="Le salon où le message sera envoyé.",
    message="Le contenu du message."
)
@discord.app_commands.autocomplete(nom_profil=autocomplete_profils)
async def envoyer_message_profil(interaction: discord.Interaction, nom_profil: str, salon_cible: discord.TextChannel, message: str):
    await interaction.response.defer(ephemeral=True)
    if nom_profil not in webhooks_perso:
        await interaction.followup.send(f"Le profil `{nom_profil}` n'existe pas. Veuillez le créer d'abord avec la commande `/creer-profil-webhook`.")
        return
    webhook_info = webhooks_perso[nom_profil]
    webhook = webhook_info["webhook"]
    avatar_url = webhook_info["avatar_url"]
    if avatar_url is None:
        avatar_url = bot.user.avatar.url
    try:
        if webhook.channel_id != salon_cible.id:
            webhooks = await salon_cible.webhooks()
            webhook_found = discord.utils.get(webhooks, name=nom_profil)
            if webhook_found:
                webhook = webhook_found
            else:
                await interaction.followup.send(f"Le profil `{nom_profil}` ne peut pas être utilisé dans ce salon car il a été créé dans {webhook.channel.mention}. Vous devez créer un nouveau profil dans ce salon si vous voulez l'utiliser ici.")
                return
        await webhook.send(
            message,
            username=nom_profil,
            avatar_url=avatar_url,
        )
        await interaction.followup.send("Message envoyé avec succès !", ephemeral=True)
    except discord.NotFound:
        del webhooks_perso[nom_profil]
        await interaction.followup.send(f"Le webhook pour le profil `{nom_profil}` n'existe plus. Il a été supprimé de la liste.")
    except Exception as e:
        await interaction.followup.send(f"Une erreur est survenue lors de l'envoi du message : {e}")

@bot.tree.command(
    name="supprimer-profil-webhook",
    description="Supprime un profil de message webhook."
)
@discord.app_commands.describe(nom_profil="Le nom du profil à supprimer.")
@discord.app_commands.autocomplete(nom_profil=autocomplete_profils)
async def supprimer_profil_webhook(interaction: discord.Interaction, nom_profil: str):
    await interaction.response.defer(ephemeral=True)
    if nom_profil not in webhooks_perso:
        await interaction.followup.send(f"Le profil `{nom_profil}` n'existe pas.")
        return
    webhook_info = webhooks_perso[nom_profil]
    webhook = webhook_info["webhook"]
    try:
        await webhook.delete()
        del webhooks_perso[nom_profil]
        await interaction.followup.send(f"Le profil `{nom_profil}` a été supprimé avec succès.")
    except discord.NotFound:
        del webhooks_perso[nom_profil]
        await interaction.followup.send(f"Le webhook pour le profil `{nom_profil}` n'existait plus sur Discord. Il a été retiré de la liste.")
    except discord.Forbidden:
        await interaction.followup.send("Je n'ai pas la permission de supprimer ce webhook.")
    except Exception as e:
        await interaction.response.send_message(f"Une erreur est survenue lors de la suppression du webhook : {e}")

@tasks.loop(seconds=3.0)
async def change_role_color():
    for guild_id in list(rainbow_roles.keys()):
        try:
            role_info = rainbow_roles[guild_id]
            role = role_info["role"]
            current_hue = role_info["current_hue"]
            current_hue += 0.025
            if current_hue >= 1.0:
                current_hue = 0.0
            rgb = colorsys.hsv_to_rgb(current_hue, 1.0, 1.0)
            r, g, b = [int(x * 255) for x in rgb]
            new_color = discord.Color.from_rgb(r, g, b)
            await role.edit(color=new_color)
            role_info["current_hue"] = current_hue
        except KeyError:
            continue
        except discord.Forbidden:
            print(f"Erreur de permission: impossible de modifier le rôle {role.name}")
            del rainbow_roles[guild_id]
        except Exception as e:
            print(f"Erreur inattendue: {e}")

@bot.tree.command(name="creer-rainbow-role", description="Applique un effet arc-en-ciel à un rôle existant.")
@discord.app_commands.describe(role="Le rôle à qui appliquer l'effet arc-en-ciel.")
@discord.app_commands.default_permissions(manage_roles=True)
async def create_rainbow_role(interaction: discord.Interaction, role: discord.Role):
    guild_id = interaction.guild.id
    if role.id == interaction.guild.me.top_role.id:
        await interaction.response.send_message("Je ne peux pas m'appliquer l'effet arc-en-ciel à moi-même.", ephemeral=True)
        return
    if guild_id in rainbow_roles:
        await interaction.response.send_message("Un effet arc-en-ciel est déjà actif sur un rôle. Utilisez `/arreter-rainbow-role` pour l'arrêter.", ephemeral=True)
        return
    if role.position >= interaction.guild.me.top_role.position:
        await interaction.response.send_message(f"Je ne peux pas modifier le rôle **{role.name}** car il est au-dessus de mon rôle dans la hiérarchie. Veuillez le déplacer en dessous de mon rôle pour que je puisse le modifier.", ephemeral=True)
        return
    try:
        rainbow_roles[guild_id] = {"role": role, "current_hue": 0.0}
        if not change_role_color.is_running():
            change_role_color.start()
        await interaction.response.send_message(f"Le rôle **{role.name}** a désormais un cycle de couleurs arc-en-ciel ! 🌈", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("Je n'ai pas la permission de gérer les rôles. Assurez-vous que mon rôle est au-dessus du rôle que vous essayez de modifier.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Une erreur s'est produite : {e}", ephemeral=True)

@bot.tree.command(name="arreter-rainbow-role", description="Arrête le cycle de couleurs et retire l'effet du rôle.")
@discord.app_commands.default_permissions(manage_roles=True)
async def stop_rainbow_role(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    if guild_id not in rainbow_roles:
        await interaction.response.send_message("Il n'y a pas de rôle arc-en-ciel actif sur ce serveur.", ephemeral=True)
        return
    del rainbow_roles[guild_id]
    if not rainbow_roles:
        change_role_color.stop()
    await interaction.response.send_message("L'effet arc-en-ciel a été retiré du rôle et le cycle de couleurs a été arrêté.", ephemeral=True)

class TicketCloseModal(Modal, title="Fermer le ticket"):
    raison = TextInput(
        label="Raison de la fermeture",
        style=discord.TextStyle.short,
        placeholder="Problème résolu, spam, etc.",
        required=False,
        max_length=100
    )

    async def on_submit(self, interaction: discord.Interaction):
        channel = interaction.channel
        raison = self.raison.value or "Aucune raison spécifiée."
        if not channel.name.startswith("ticket-"):
            await interaction.response.send_message("Ce salon n'est pas un ticket.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            ticket_creator_id_str = channel.topic.split('(ID: ')[1].split(')')[0]
            ticket_creator = interaction.guild.get_member(int(ticket_creator_id_str))
        except (IndexError, ValueError):
            ticket_creator = None
        await channel.edit(name=f"closed-{channel.name}")
        if ticket_creator:
            await channel.set_permissions(ticket_creator, view_channel=False)
        embed = discord.Embed(
            title="Ticket fermé",
            description=f"Le ticket a été fermé par {interaction.user.mention}.",
            color=discord.Color.red()
        )
        embed.add_field(name="Raison", value=raison, inline=False)
        view = View()
        view.add_item(Button(label="Sauvegarder et Supprimer", style=discord.ButtonStyle.blurple, custom_id="ticket_save_and_delete"))
        view.add_item(Button(label="Réouvrir le Ticket", style=discord.ButtonStyle.green, custom_id="ticket_reopen"))
        await interaction.followup.send(embed=embed, view=view)

class TicketSelect(Select):
    def __init__(self, category_id: int, options_json: str, roles_visibles_ids: list):
        super().__init__(placeholder="Choisissez la raison de votre ticket...", custom_id="ticket_select_menu")
        self.category_id = category_id
        self.roles_visibles_ids = roles_visibles_ids
        self.options_data = []
        if options_json:
            try:
                self.options_data = json.loads(options_json)
            except json.JSONDecodeError as e:
                print(f"Erreur de décodage JSON dans TicketSelect: {e}")
        for item in self.options_data:
            emoji_value = item.get('emoji', None)
            label = item.get('label', 'Sans label')
            description = item.get('description', None)
            if emoji_value and emoji_value.startswith('<') and emoji_value.endswith('>'):
                try:
                    emoji = discord.PartialEmoji.from_str(emoji_value)
                    self.add_option(label=label, description=description, emoji=emoji, value=label)
                except Exception as e:
                    print(f"Erreur lors de la gestion de l'emoji personnalisé: {e}")
                    self.add_option(label=label, description=description, emoji=None, value=label)
            else:
                self.add_option(label=label, description=description, emoji=emoji_value, value=label)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user = interaction.user
        guild = interaction.guild
        selected_option_label = self.values[0]
        selected_option_data = next((item for item in self.options_data if item['label'] == selected_option_label), None)
        if not selected_option_data:
            await interaction.followup.send("Une erreur est survenue lors de la sélection de votre option. Données de l'option introuvables. Veuillez contacter un administrateur.", ephemeral=True)
            print(f"Erreur: Données de l'option non trouvées pour le label '{selected_option_label}'")
            return
        roles_to_ping_ids = selected_option_data.get('roles_ping_ids', [])
        for channel in guild.channels:
            if isinstance(channel, discord.TextChannel) and channel.topic and f"ticket-{user.id}" in channel.topic:
                await interaction.followup.send(f"Vous avez déjà un ticket ouvert dans {channel.mention}.", ephemeral=True)
                return
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
        }
        for role_id in self.roles_visibles_ids:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True)
        category = discord.utils.get(guild.categories, id=self.category_id)
        if not category:
            await interaction.followup.send("La catégorie de tickets n'a pas été trouvée. Veuillez vérifier la configuration.", ephemeral=True)
            return
        ticket_channel = await category.create_text_channel(
            name=f"ticket-{user.name}",
            topic=f"Ticket de {user.name} (ID: {user.id}) | Raison: {selected_option_label}",
            overwrites=overwrites
        )
        ticket_embed = discord.Embed(
            title=selected_option_label,
            description=f"Ticket de {user.mention}",
            color=discord.Color.blue()
        )
        ticket_embed.add_field(name="Problème", value="Veuillez décrire votre problème en détail.\n\nUn membre du staff vous aidera bientôt.", inline=False)
        ticket_manage_view = View()
        ticket_manage_view.add_item(Button(label="Fermer le Ticket", style=discord.ButtonStyle.red, custom_id="ticket_close_button"))
        ticket_manage_view.add_item(Button(label="Claim", style=discord.ButtonStyle.green, custom_id="ticket_claim"))
        role_mentions = " ".join([f"<@&{r}>" for r in roles_to_ping_ids])
        await ticket_channel.send(content=f"{role_mentions} {user.mention}", embed=ticket_embed, view=ticket_manage_view)
        await interaction.followup.send(f"Votre ticket a été créé dans {ticket_channel.mention}.", ephemeral=True)

class TicketCreationModal(Modal, title="Ouvrir un ticket"):
    def __init__(self, category_id: int, roles_ping_ids: str, roles_visibles_ids: list):
        super().__init__(custom_id="ticket_creation_modal")
        self.category_id = category_id
        self.roles_ping_ids = roles_ping_ids
        self.roles_visibles_ids = roles_visibles_ids
        self.ticket_title = TextInput(
            label="Titre du ticket (raison d'ouverture)",
            placeholder="Décrivez brièvement la raison de votre ticket.",
            required=True,
            max_length=50
        )
        self.add_item(self.ticket_title)
        
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user = interaction.user
        guild = interaction.guild
        for channel in guild.channels:
            if isinstance(channel, discord.TextChannel) and channel.topic and f"ticket-{user.id}" in channel.topic:
                await interaction.followup.send(f"Vous avez déjà un ticket ouvert dans {channel.mention}.", ephemeral=True)
                return
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
        }
        roles_to_ping = [int(r) for r in self.roles_ping_ids.split(',') if r.isdigit()]
        for role_id in self.roles_visibles_ids:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True)
        category = discord.utils.get(guild.categories, id=self.category_id)
        if not category:
            await interaction.followup.send("La catégorie de tickets n'a pas été trouvée. Veuillez vérifier la configuration.", ephemeral=True)
            return
        ticket_channel = await category.create_text_channel(
            name=f"ticket-{user.name}",
            topic=f"Ticket de {user.name} (ID: {user.id}) | Raison: {self.ticket_title.value}",
            overwrites=overwrites
        )
        ticket_embed = discord.Embed(
            title=self.ticket_title.value,
            description=f"Ticket de {user.mention}",
            color=discord.Color.blue()
        )
        ticket_embed.add_field(name="Problème", value="Veuillez décrire votre problème en détail.\n\nUn membre du staff vous aidera bientôt.", inline=False)
        ticket_manage_view = View()
        ticket_manage_view.add_item(Button(label="Fermer le Ticket", style=discord.ButtonStyle.red, custom_id="ticket_close_button"))
        ticket_manage_view.add_item(Button(label="Claim", style=discord.ButtonStyle.green, custom_id="ticket_claim"))
        role_mentions = " ".join([f"<@&{r}>" for r in roles_to_ping])
        await ticket_channel.send(content=f"{role_mentions} {user.mention}", embed=ticket_embed, view=ticket_manage_view)
        await interaction.followup.send(f"Votre ticket a été créé dans {ticket_channel.mention}.", ephemeral=True)

class OpenTicketButton(Button):
    def __init__(self, category_id: int, roles_ping_ids: str, roles_visibles_ids: list):
        super().__init__(label="Ouvrir un Ticket", style=discord.ButtonStyle.secondary, emoji="📩", custom_id="open_ticket_button")
        self.category_id = category_id
        self.roles_ping_ids = roles_ping_ids
        self.roles_visibles_ids = roles_visibles_ids
    async def callback(self, interaction: discord.Interaction):
        modal = TicketCreationModal(category_id=self.category_id, roles_ping_ids=self.roles_ping_ids, roles_visibles_ids=self.roles_visibles_ids)
        await interaction.response.send_modal(modal)

class TicketView(View):
    def __init__(self, category_id: int, roles_ping_ids: str, mode: str, roles_visibles_ids: list, selector_content: str = None):
        super().__init__(timeout=None)
        self.category_id = category_id
        self.roles_ping_ids = roles_ping_ids
        self.roles_visibles_ids = roles_visibles_ids
        if mode == 'button':
            self.add_item(OpenTicketButton(self.category_id, self.roles_ping_ids, self.roles_visibles_ids))
        elif mode == 'selector':
            self.add_item(TicketSelect(self.category_id, selector_content, self.roles_visibles_ids))
            
@bot.tree.command(name="ticket-setup", description="Crée un panneau de ticket personnalisable.")
@describe(
    salon_panel="Le salon où le panneau de ticket sera affiché.",
    category_tickets="La catégorie où les tickets seront créés.",
    titre="Le titre de l'embed.",
    description_embed="La description de l'embed.",
    mode="Choisissez 'bouton' pour un bouton ou 'sélecteur' pour un menu déroulant.",
    roles_ping_ids="IDs des rôles à pinguer (séparés par des virgules, facultatif).",
    selecteur_contenu_json="Contenu du sélecteur au format JSON (ex: [{'label':'Raison 1'}, {'label':'Raison 2'}]) (si mode=selecteur).",
    roles_visibles="IDs des rôles qui peuvent voir les tickets (séparés par des virgules, facultatif).",
    image_url="L'URL de l'image de l'embed (facultatif).",
    couleur_hex="La couleur hexadécimale de l'embed (ex: #FF5733, facultatif).",
    profil_nom="Le nom du profil personnalisé à utiliser (facultatif)."
)
@discord.app_commands.choices(mode=[
    discord.app_commands.Choice(name="bouton", value="button"),
    discord.app_commands.Choice(name="sélecteur", value="selector")
])
@discord.app_commands.default_permissions(manage_channels=True)
async def ticket_setup(
    interaction: discord.Interaction,
    salon_panel: discord.TextChannel,
    category_tickets: discord.CategoryChannel,
    titre: str,
    description_embed: str,
    mode: str,
    roles_ping_ids: str = None,
    selecteur_contenu_json: str = None,
    roles_visibles: str = None,
    image_url: str = None,
    couleur_hex: str = None,
    profil_nom: str = None
):
    await interaction.response.defer(ephemeral=True)
    try:
        if mode == 'selector' and not selecteur_contenu_json:
            await interaction.followup.send("Vous devez fournir le contenu JSON pour le mode 'sélecteur'.", ephemeral=True)
            return
        color = None
        if couleur_hex:
            couleur_hex = couleur_hex.lstrip('#')
            if len(couleur_hex) == 6:
                color = discord.Color(int(couleur_hex, 16))
            else:
                await interaction.followup.send("La couleur hexadécimale est invalide. Utilisez le format #RRGGBB.", ephemeral=True)
                return
        embed = discord.Embed(title=titre, description=description_embed, color=color or discord.Color.default())
        if image_url:
            embed.set_image(url=image_url)
        roles_visibles_ids = [int(r) for r in roles_visibles.split(',') if r.isdigit()] if roles_visibles else []
        webhook_info = webhooks_perso.get(profil_nom)
        view = TicketView(category_tickets.id, roles_ping_ids, mode, roles_visibles_ids, selecteur_contenu_json)
        message = None
        if webhook_info and webhook_info["webhook"].channel_id == salon_panel.id:
            webhook = webhook_info["webhook"]
            message = await webhook.send(embed=embed, username=profil_nom, avatar_url=webhook_info["avatar_url"], view=view, wait=True)
        else:
            message = await salon_panel.send(embed=embed, view=view)
            if profil_nom and not webhook_info:
                await interaction.followup.send(f"Le profil `{profil_nom}` n'a pas été trouvé. Le panneau de ticket a été envoyé avec le profil par défaut.", ephemeral=True)
            elif profil_nom and webhook_info and webhook_info["webhook"].channel_id != salon_panel.id:
                 await interaction.followup.send(f"Le profil `{profil_nom}` a été créé dans un autre salon. Le panneau de ticket a été envoyé avec le profil par défaut.", ephemeral=True)
        
        panel_data = {
            "channel_id": salon_panel.id,
            "message_id": message.id,
            "category_id": category_tickets.id,
            "roles_ping_ids": roles_ping_ids,
            "mode": mode,
            "roles_visibles_ids": roles_visibles_ids,
            "selector_content": selecteur_contenu_json
        }
        bot_data["ticket_panels"].append(panel_data)
        save_data(bot_data)
        
        await interaction.followup.send(f"Le panneau de ticket a été envoyé dans {salon_panel.mention}.", ephemeral=True)
    
    except Exception as e:
        await interaction.followup.send(f"Une erreur s'est produite : {e}", ephemeral=True)

@bot.tree.command(name="set-ticket-log-channel", description="Définit le salon où les logs de tickets seront envoyés.")
@describe(channel="Le salon de logs des tickets.")
@discord.app_commands.default_permissions(manage_channels=True)
async def set_ticket_log_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    bot_data["ticket_logs"][str(interaction.guild.id)] = str(channel.id)
    save_data(bot_data)
    await interaction.response.send_message(f"Le salon de logs des tickets a été défini sur {channel.mention}.", ephemeral=True)

@bot.tree.command(name="delete-ticket", description="Supprime un ticket (action immédiate).")
@discord.app_commands.default_permissions(manage_channels=True)
async def delete_ticket(interaction: discord.Interaction):
    channel = interaction.channel
    if not channel.name.startswith("ticket-") and not channel.name.startswith("closed-"):
        await interaction.response.send_message("Cette commande ne peut être utilisée que dans un ticket.", ephemeral=True)
        return
    await interaction.response.send_message("Suppression du ticket...", ephemeral=True)
    await channel.delete()

@bot.tree.command(name="set-log-channel", description="Définit le salon où les logs du bot seront envoyés.")
@describe(channel="Le salon de logs.")
@discord.app_commands.default_permissions(manage_channels=True)
async def set_log_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    guild_id = str(interaction.guild.id)
    log_channels[guild_id] = str(channel.id)
    bot_data["log_channels"] = log_channels
    save_data(bot_data)
    await interaction.response.send_message(f"Le salon de logs du bot a été défini sur {channel.mention}.", ephemeral=True)

# Commande pour configurer le panneau d'autorôle basé sur les réactions
@bot.tree.command(name="setup-reaction-role", description="Configure un panneau d'autorôle basé sur les réactions.")
@describe(
    message_text="Le texte du panneau d'autorôle.",
    roles_json="Une chaîne JSON qui définit les emojis et les rôles (ex: [{'emoji':'🎉','role_id':123456789012345678}])"
)
async def setup_reaction_role(interaction: discord.Interaction, message_text: str, roles_json: str):
    global REACTION_MESSAGE_ID, EMOJI_TO_ROLE
    
    await interaction.response.defer(ephemeral=True)

    try:
        roles_data = json.loads(roles_json)
        EMOJI_TO_ROLE.clear()

        embed = discord.Embed(
            title="Système d'Auto-Rôle",
            description=message_text,
            color=discord.Color.blue()
        )
        
        reaction_text = ""
        for item in roles_data:
            emoji = item.get('emoji')
            role_id = item.get('role_id')
            if not emoji or not role_id:
                await interaction.followup.send("Le format JSON est invalide. Chaque élément doit avoir 'emoji' et 'role_id'.", ephemeral=True)
                return

            role = interaction.guild.get_role(role_id)
            if not role:
                await interaction.followup.send(f"Le rôle avec l'ID {role_id} n'a pas été trouvé.", ephemeral=True)
                return
            
            EMOJI_TO_ROLE[emoji] = role_id
            reaction_text += f"{emoji}: **{role.name}**\n"
        
        embed.add_field(name="Rôles Disponibles", value=reaction_text)

        message = await interaction.channel.send(embed=embed)
        for emoji in EMOJI_TO_ROLE.keys():
            await message.add_reaction(emoji)
        
        REACTION_MESSAGE_ID = message.id
        await interaction.followup.send("Le panneau d'autorôle a été configuré avec succès !", ephemeral=True)

    except json.JSONDecodeError:
        await interaction.followup.send("Format JSON invalide. Veuillez vérifier la syntaxe.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Une erreur est survenue : {e}", ephemeral=True)

@bot.event
async def on_raw_reaction_add(payload):
    if payload.message_id != REACTION_MESSAGE_ID or payload.member.bot:
        return

    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return
        
    role_id = EMOJI_TO_ROLE.get(str(payload.emoji))
    if role_id:
        member = guild.get_member(payload.user_id)
        role = guild.get_role(role_id)
        if member and role:
            try:
                await member.add_roles(role)
                print(f"Rôle {role.name} donné à {member.display_name}")
            except discord.Forbidden:
                print(f"Erreur de permissions: impossible de donner le rôle.")
            except Exception as e:
                print(f"Erreur lors de l'attribution du rôle: {e}")

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.message_id != REACTION_MESSAGE_ID:
        return
    
    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return
        
    role_id = EMOJI_TO_ROLE.get(str(payload.emoji))
    if role_id:
        member = guild.get_member(payload.user_id)
        role = guild.get_role(role_id)
        if member and role:
            try:
                await member.remove_roles(role)
                print(f"Rôle {role.name} retiré de {member.display_name}")
            except discord.Forbidden:
                print(f"Erreur de permissions: impossible de retirer le rôle.")
            except Exception as e:
                print(f"Erreur lors du retrait du rôle: {e}")

# Vue et bouton pour le panneau de rôle
class RoleButtonView(View):
    def __init__(self, role_id: int):
        super().__init__(timeout=None)
        self.role_id = role_id

    @discord.ui.button(label="Obtenir le Rôle", style=discord.ButtonStyle.primary, custom_id="role_button")
    async def role_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = interaction.guild.get_role(self.role_id)
        if not role:
            await interaction.response.send_message("Le rôle n'a pas été trouvé.", ephemeral=True)
            return

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"Le rôle **{role.name}** vous a été retiré.", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"Le rôle **{role.name}** vous a été donné.", ephemeral=True)

# Commande pour créer le panneau de rôles avec un bouton
@bot.tree.command(name="role-button", description="Crée un panneau pour obtenir un rôle via un bouton.")
@describe(
    salon="Le salon où le panneau sera envoyé.",
    titre="Le titre de l'embed du panneau de rôles.",
    description_message="Le contenu du message.",
    role="Le rôle à donner/retirer.",
    texte_bouton="Le texte affiché sur le bouton.",
    couleur_bouton="La couleur du bouton (bleu, gris, vert, rouge).",
    profil_nom="Le nom du profil webhook personnalisé (facultatif)."
)
@discord.app_commands.choices(couleur_bouton=[
    discord.app_commands.Choice(name="Bleu (Primaire)", value="primary"),
    discord.app_commands.Choice(name="Gris (Secondaire)", value="secondary"),
    discord.app_commands.Choice(name="Vert (Succès)", value="success"),
    discord.app_commands.Choice(name="Rouge (Danger)", value="danger")
])
@discord.app_commands.default_permissions(manage_roles=True)
async def role_button_command(
    interaction: discord.Interaction,
    salon: discord.TextChannel,
    titre: str,
    description_message: str,
    role: discord.Role,
    texte_bouton: str,
    couleur_bouton: str,
    profil_nom: str = None
):
    await interaction.response.defer(ephemeral=True)

    try:
        if role.position >= interaction.guild.me.top_role.position:
            await interaction.followup.send("Je ne peux pas gérer ce rôle car il est au-dessus du mien dans la hiérarchie. Veuillez déplacer mon rôle au-dessus.", ephemeral=True)
            return

        button_style_map = {
            "primary": discord.ButtonStyle.primary,
            "secondary": discord.ButtonStyle.secondary,
            "success": discord.ButtonStyle.success,
            "danger": discord.ButtonStyle.danger
        }
        
        view = RoleButtonView(role_id=role.id)
        view.children[0].label = texte_bouton
        view.children[0].style = button_style_map.get(couleur_bouton, discord.ButtonStyle.primary)
        
        embed = discord.Embed(
            title=titre,
            description=description_message,
            color=role.color
        )

        webhook_info = webhooks_perso.get(profil_nom)
        if webhook_info and webhook_info["webhook"].channel_id == salon.id:
            webhook = webhook_info["webhook"]
            await webhook.send(
                embed=embed,
                username=profil_nom,
                avatar_url=webhook_info["avatar_url"],
                view=view
            )
        else:
            await salon.send(embed=embed, view=view)
            if profil_nom:
                await interaction.followup.send(f"Le profil '{profil_nom}' n'a pas été trouvé ou n'est pas dans le bon salon. Le panneau a été envoyé avec le profil par défaut du bot.", ephemeral=True)
        
        await interaction.followup.send("Panneau de rôle envoyé avec succès !", ephemeral=True)
        
    except Exception as e:
        await interaction.followup.send(f"Une erreur s'est produite lors de la création du panneau : {e}", ephemeral=True)

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        custom_id = interaction.data['custom_id']
        if custom_id == "ticket_close_button":
            await interaction.response.send_modal(TicketCloseModal())
        elif custom_id == "ticket_claim":
            await handle_claim_ticket(interaction)
        elif custom_id == "ticket_reopen":
            await handle_reopen_ticket(interaction)
        elif custom_id == "ticket_save_and_delete":
            await handle_save_and_delete_ticket(interaction)

keep_alive()
bot.run(token)


