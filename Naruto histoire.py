import discord
import os
from discord import app_commands
from dotenv import load_dotenv
from keep_alive import keep_alive

load_dotenv()
token = os.getenv('DISCORD_TOKEN')
# Remplacez 'VOTRE_JETON_DE_BOT' par le jeton de votre bot

# Configurez le bot avec les "Intents" requis
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

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

keep_alive()
client.run(token)