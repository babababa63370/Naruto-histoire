import discord
from discord.ext import commands, tasks
import os
import json
import colorsys
from discord.ui import Button, View, Modal, TextInput, Select
from discord.app_commands import describe
from dotenv import load_dotenv
from keep_alive import keep_alive
import asyncio

load_dotenv()
token = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

webhooks_perso = {}
ticket_logs = {}
rainbow_roles = {}
bot_data = {} # Variable globale pour la persistance des données

# Fichier pour la persistance des données
DATA_FILE = "data.json"

def save_data(data):
    """Sauvegarde les données dans un fichier JSON."""
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def load_data():
    """Charge les données depuis un fichier JSON."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {"ticket_panels": [], "ticket_logs": {}}


# Fonctions utilitaires
def chunk_text(text, chunk_size=1900):
    """
    Découpe une longue chaîne de caractères en morceaux plus petits.
    """
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

# Fonctions de gestion des tickets
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

# Événements du bot
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f'Connecté en tant que {bot.user}')
    print('Le bot est prêt à utiliser les commandes slash.')
    
    # --- AJOUT IMPORTANT POUR LA PERSISTANCE ---
    global bot_data
    bot_data = load_data()
    
    # Ajout des vues persistantes pour chaque panneau de ticket
    for panel in bot_data.get("ticket_panels", []):
        view = TicketView(
            category_id=panel['category_id'],
            roles_ping_ids=panel['roles_ping_ids'],
            mode=panel['mode'],
            roles_visibles_ids=panel['roles_visibles_ids'],
            selector_content=panel.get('selector_content')
        )
        bot.add_view(view)
    # --- FIN DE L'AJOUT ---


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

# Commandes de gestion des webhooks
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
        await interaction.followup.send(f"Une erreur est survenue lors de la suppression du webhook : {e}")

# Fonctions liées aux rôles
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

# Classes de gestion des tickets
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
            
# Commandes de ticket
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
        if webhook_info and webhook_info["webhook"].channel_id == salon_panel.id:
            webhook = webhook_info["webhook"]
            await webhook.send(embed=embed, username=profil_nom, avatar_url=webhook_info["avatar_url"], view=view)
        else:
            message = await salon_panel.send(embed=embed, view=view)
            if profil_nom and not webhook_info:
                await interaction.followup.send(f"Le profil `{profil_nom}` n'a pas été trouvé. Le panneau de ticket a été envoyé avec le profil par défaut.", ephemeral=True)
            elif profil_nom and webhook_info and webhook_info["webhook"].channel_id != salon_panel.id:
                 await interaction.followup.send(f"Le profil `{profil_nom}` a été créé dans un autre salon. Le panneau de ticket a été envoyé avec le profil par défaut.", ephemeral=True)

        # --- AJOUT IMPORTANT POUR LA PERSISTANCE ---
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
        # --- FIN DE L'AJOUT ---
        
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

# Événement pour gérer les interactions avec les boutons
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

# Point d'entrée
keep_alive()
bot.run(token)
