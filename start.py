import discord
import os
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv
from keep_alive import keep_alive
import colorsys

load_dotenv()
token = os.getenv('DISCORD_TOKEN')
# Remplacez 'VOTRE_JETON_DE_BOT' par le jeton de votre bot

# Configurez le bot avec les "Intents" requis
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

bot = commands.Bot(command_prefix='!', intents=intents)

# Créez l'arbre de commandes pour les commandes de type "slash"
tree = app_commands.CommandTree(client)

def chunk_text(text, chunk_size=1900):
    """
    Découpe une longue chaîne de caractères en morceaux plus petits.
    On utilise 1900 pour laisser de la marge pour l'en-tête et les blocs de code.
    """
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

@client.event
async def on_ready():
    """
    Cet événement se déclenche lorsque le bot se connecte à Discord.
    """
    await tree.sync()
    print(f'Connecté en tant que {client.user}')
    print('Le bot est prêt à utiliser les commandes slash.')

@tree.command(
    name="get_messages_du_salon",
    description="Récupère et concatène tous les messages d'un salon."
)
@app_commands.describe(
    salon="Le salon dont il faut lire les messages."
)
async def get_messages_command(interaction: discord.Interaction, salon: discord.TextChannel):
    """
    Ceci est le gestionnaire de la commande slash.
    """
    # Utiliser defer() sans ephemeral=True pour que le message soit public
    await interaction.response.defer()

    try:
        messages = []
        async for message in salon.history(limit=None):
            messages.append(message.content)

        if not messages:
            await interaction.followup.send(f"Je n'ai trouvé aucun message dans {salon.mention}.")
            return

        messages.reverse()
        # Concaténer les messages avec un espace pour les aligner
        messages_concatenees = " ".join(messages)

        # Diviser le message en morceaux de taille sûre
        message_chunks = chunk_text(messages_concatenees)

        # En-tête du message
        header = f"**Messages de {salon.mention} :**"
        
        # Le premier message est une réponse à l'interaction
        await interaction.followup.send(f"{header}\n```\n{message_chunks[0]}\n```")

        # Envoyer les morceaux restants dans des messages séparés
        for chunk in message_chunks[1:]:
            await interaction.channel.send(f"```\n{chunk}\n```")
            
    except discord.Forbidden:
        await interaction.followup.send(f"Je n'ai pas la permission de lire les messages dans {salon.mention}.")
    except Exception as e:
        await interaction.followup.send(f"Une erreur s'est produite : {e}")

rainbow_roles = {}

# La tâche en arrière-plan pour faire cycler la couleur du rôle
@tasks.loop(seconds=3.0)  # Le changement de couleur se fera une fois toutes les 3 secondes
async def change_role_color():
    # Pour chaque serveur qui a un rôle arc-en-ciel
    for guild_id in list(rainbow_roles.keys()):
        try:
            role_info = rainbow_roles[guild_id]
            role = role_info["role"]
            current_hue = role_info["current_hue"]
            
            # Incrémente la teinte. 0.025 est un bon ajustement pour 3 secondes.
            current_hue += 0.025
            if current_hue >= 1.0:
                current_hue = 0.0
            
            # Conversion de la teinte (HSV) en RGB
            rgb = colorsys.hsv_to_rgb(current_hue, 1.0, 1.0)
            
            # Conversion des valeurs RGB de 0-1 à 0-255
            r, g, b = [int(x * 255) for x in rgb]
            
            # Crée l'objet discord.Color
            new_color = discord.Color.from_rgb(r, g, b)
            
            # Met à jour la couleur du rôle
            await role.edit(color=new_color)
            
            # Met à jour la teinte dans le dictionnaire
            role_info["current_hue"] = current_hue
            
        except KeyError:
            # Gère les cas où le rôle n'existe plus
            continue
        except discord.Forbidden:
            # Gère les erreurs de permission et stoppe la tâche pour ce serveur
            print(f"Erreur de permission: impossible de modifier le rôle {role.name}")
            del rainbow_roles[guild_id]
        except Exception as e:
            print(f"Erreur inattendue: {e}")

# Commande slash pour appliquer un effet arc-en-ciel à un rôle existant
@bot.tree.command(name="creer-rainbow-role", description="Applique un effet arc-en-ciel à un rôle existant.")
@app_commands.describe(role="Le rôle à qui appliquer l'effet arc-en-ciel.")
@app_commands.default_permissions(manage_roles=True)
async def create_rainbow_role(interaction: discord.Interaction, role: discord.Role):
    guild_id = interaction.guild.id
    
    # Vérifie si le rôle à modifier n'est pas le rôle du bot
    if role.id == interaction.guild.me.top_role.id:
        await interaction.response.send_message("Je ne peux pas m'appliquer l'effet arc-en-ciel à moi-même.", ephemeral=True)
        return

    # Vérifie si un rôle arc-en-ciel est déjà actif sur ce serveur
    if guild_id in rainbow_roles:
        await interaction.response.send_message("Un effet arc-en-ciel est déjà actif sur un rôle. Utilisez `/arreter-rainbow-role` pour l'arrêter.", ephemeral=True)
        return
        
    # Vérifie si la position du rôle est inférieure à celle du bot
    if role.position >= interaction.guild.me.top_role.position:
        await interaction.response.send_message(f"Je ne peux pas modifier le rôle **{role.name}** car il est au-dessus de mon rôle dans la hiérarchie. Veuillez le déplacer en dessous de mon rôle pour que je puisse le modifier.", ephemeral=True)
        return
    
    try:
        # Initialise la teinte et la tâche pour ce rôle
        rainbow_roles[guild_id] = {"role": role, "current_hue": 0.0}
        
        # La boucle est démarrée une seule fois et gère tous les rôles
        if not change_role_color.is_running():
            change_role_color.start()
        
        await interaction.response.send_message(f"Le rôle **{role.name}** a désormais un cycle de couleurs arc-en-ciel ! 🌈", ephemeral=True)
    
    except discord.Forbidden:
        await interaction.response.send_message("Je n'ai pas la permission de gérer les rôles. Assurez-vous que mon rôle est au-dessus du rôle que vous essayez de modifier.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Une erreur s'est produite : {e}", ephemeral=True)

# Commande slash pour arrêter le rôle arc-en-ciel
@bot.tree.command(name="arreter-rainbow-role", description="Arrête le cycle de couleurs et retire l'effet du rôle.")
@app_commands.default_permissions(manage_roles=True)
async def stop_rainbow_role(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    
    if guild_id not in rainbow_roles:
        await interaction.response.send_message("Il n'y a pas de rôle arc-en-ciel actif sur ce serveur.", ephemeral=True)
        return
    
    del rainbow_roles[guild_id]
    
    # Si plus aucun rôle n'est géré, on arrête la boucle
    if not rainbow_roles:
        change_role_color.stop()
    
    await interaction.response.send_message("L'effet arc-en-ciel a été retiré du rôle et le cycle de couleurs a été arrêté.", ephemeral=True)

keep_alive()
client.run(token)
