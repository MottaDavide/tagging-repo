# Swagger-UI

*CoolPKG* è basato su **FastAPI** che nativamente mette a disposizione una documentazione interattiva basata su [swagger-ui](https://fastapi.tiangolo.com/features/#automatic-docs) per codice ed api.
Sarà sufficiente commentare i vari endpoint realizzati con `docstring` ossia all'interno del triplo apice """  """ e il tutto risulterà visibile sotto `localhost:9999/docs`
Nota che, come indicato in [documentazione](https://fastapi.tiangolo.com/advanced/path-operation-advanced-configuration/#advanced-description-from-docstring) potrai aggiungere `\f` per poter interrompere il rendering del commento.
In questo modo le indicazioni pubbliche e private saranno nello stesso posto.

Qui un esempio:

```python
@app.post("/items/", response_model=Item, summary="Create an item")
async def create_item(item: Item):
    """
    Create an item with all the information:

    - **name**: each item must have a name
    - **description**: a long description
    - **price**: required
    - **tax**: if the item doesn't have tax, you can omit this
    - **tags**: a set of unique tag strings for this item
    \f
    :param item: User input.
    """
    return item
```

Il resto dopo `\f` non sarà visibile agli utenti finali.
