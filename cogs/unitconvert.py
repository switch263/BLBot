import discord
from discord.ext import commands
import pint

class UnitConverter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ureg = pint.UnitRegistry()

    @commands.command(help='Converts units: !convert <value> <from_unit> <to_unit>')
    async def convert(self, ctx, value: float, unit_from: str, unit_to: str):
        try:
            # Check if this is a temperature conversion and handle accordingly
            if unit_from in ["fahrenheit", "F", "degree_Fahrenheit"] and unit_to in ["celsius", "C", "degree_Celsius"]:
                temp = pint.Quantity(value, self.ureg.degree_Fahrenheit)
                converted_temp = temp.to(self.ureg.degree_Celsius)
                friendly_from = "Fahrenheit"
                friendly_to = "Celsius"
            elif unit_from in ["celsius", "C", "degree_Celsius"] and unit_to in ["fahrenheit", "F", "degree_Fahrenheit"]:
                temp = pint.Quantity(value, self.ureg.degree_Celsius)
                converted_temp = temp.to(self.ureg.degree_Fahrenheit)
                friendly_from = "Celsius"
                friendly_to = "Fahrenheit"
            else:
                # Create a quantity object with the source unit
                quantity = pint.Quantity(value, self.ureg(unit_from))
                # Convert to the target unit
                converted_temp = quantity.to(unit_to)
                # Use Pint's units to get the unit names
                friendly_from = str(quantity.units)
                friendly_to = str(converted_temp.units)

            # Send the result back to the Discord channel
            await ctx.send(f"{value} {friendly_from} is {converted_temp.magnitude:.2f} {friendly_to}")
        except Exception as e:
            # Send an error message if something goes wrong (e.g., invalid units)
            await ctx.send(str(e))

def setup(bot):
    bot.add_cog(UnitConverter(bot))

