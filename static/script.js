function createRecipeResult(image, text, title, id, parentContainer, isAdmin) {
    console.log("render recipes")
    var imgEl = document.createElement("img");
    imgEl.src = image

    var textEl = document.createElement("p");
    textEl.innerText = text

    var titleEl = document.createElement("h1");
    titleEl.innerText = title

    var editLink = document.createElement("a");
    editLink.innerText = "Edit"
    editLink.href = "/recipe-edit/" + id

    var deleteLink = document.createElement("button");
    deleteLink.innerText = "Delete"

    var actions = document.createElement("div");
    actions.className = "recipe-actions"
    actions.appendChild(deleteLink)
    actions.appendChild(editLink)

    var headers = document.createElement("div");
    headers.className = "recipe-header"
    headers.appendChild(titleEl)

    deleteLink.onclick = () => {
        fetch("http://localhost:8081/api/v1/recipes/" + id, {"method": "DELETE", body: {"id": id}})
        .then(res => {
            console.log("del")

            window.location.href = "/"
        })
        .catch(er => {
        })
    }
    var recipeEl = document.createElement("div");
    recipeEl.className = "recipe"

    var recipeGroupEl = document.createElement("div");
    recipeGroupEl.className = "recipe-group"

    var recipeImgEl = document.createElement("div");
    recipeImgEl.className = "recipe-img"
    recipeImgEl.appendChild(imgEl)

    if (isAdmin) {
//        recipeGroupEl.appendChild(editLink);
//        recipeGroupEl.appendChild(deleteLink);

//        actions.appendChild(editLink)
//        actions.appendChild(deleteLink)
            headers.appendChild(actions)
    }

    recipeGroupEl.appendChild(headers);
    recipeGroupEl.appendChild(textEl);

    recipeEl.appendChild(recipeImgEl);
    recipeEl.appendChild(recipeGroupEl)

    parentContainer.appendChild(recipeEl)
}
function fetchData(formData, error) {
    var search_btn = document.getElementById("search_btn")
    var loading = document.getElementById("loading")
    var formReset = document.getElementById("reset-btn")

    loading.style.display = 'block'
    search_btn.disabled = true;
    formReset.disabled = true;

    fetch("http://localhost:8081/api/v2/search", {
            method:"POST",
            body: formData
        })
        .then(async (resp) => {
            if(!resp.ok) {
                container.appendChild(error)
                console.error(resp)
                var err = await resp.json()
                console.error(err)
                throw err
            }
            error.remove()
            return await resp.json()
        })
        .then(data => {
            console.log(data)
            results.innerHTML = ""
            data.forEach(r => {
                loading.style.display = 'none';
                search_btn.disabled = false;
                formReset.disabled = false;
                createRecipeResult(r.image_path, r['text'], r['title'],r.id, results, r['is_admin'])
            })
        })
        .catch(err => {
            if (err instanceof TypeError) {
                error.innerText = "Connection problem, try again. "
                return
            }
            console.error(err)
            loading.style.display = 'none'

            error.innerText = err.detail
        search_btn.disabled = false;
        formReset.disabled = false;
        })
}

document.addEventListener("DOMContentLoaded", () => {
    var results = document.getElementById("results");
    var container = document.getElementById("container");
    var error = document.createElement("p");
    var uploadForm = document.getElementById("uform")
    var submittedFile = document.querySelector("input[type='file']")
    var previewImg = document.getElementById("preview")
    var formReset = document.getElementById("reset-btn")


    submittedFile.addEventListener("change", () => {
    const [file] = submittedFile.files
       console.log(submittedFile)
       if (file) {
        previewImg.src = URL.createObjectURL(file)
        previewImg.style.display = "block"
       }
    })
    formReset.addEventListener("click", () => {
        uploadForm.reset()
       previewImg.src = ""
        previewImg.style.display = "none"

        results.innerText = ""
    })
    uploadForm.addEventListener("submit", (e) => {
       e.preventDefault()
        error.innerText = ''

       var formData = new FormData(uploadForm)
       fetchData(formData, error)
    })
})
